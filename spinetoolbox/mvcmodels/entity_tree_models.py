######################################################################################################################
# Copyright (C) 2017 - 2019 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Models to represent entities in a tree.

:authors: P. Vennström (VTT), M. Marin (KTH)
:date:   11.3.2019
"""
from PySide2.QtCore import Qt, Signal, Slot, QAbstractItemModel, QModelIndex
from PySide2.QtGui import QIcon
from .entity_tree_item import (
    TreeItem,
    ObjectTreeRootItem,
    ObjectClassItem,
    ObjectItem,
    RelationshipTreeRootItem,
    RelationshipClassItem,
    RelationshipItem,
)


class EntityTreeModel(QAbstractItemModel):
    """Base class for all entity tree models."""

    remove_selection_requested = Signal(name="remove_selection_requested")

    def __init__(self, parent, db_maps):
        """Init class.

        Args:
            parent (DataStoreForm)
            db_maps (dict): maps db names to DiffDatabaseMapping instances
        """
        super().__init__(parent)
        self._parent = parent
        self.db_maps = db_maps
        self._invisible_root_item = TreeItem()
        self._root_item = None
        self._db_map_data = {db_map: {"database": database} for database, db_map in db_maps.items()}
        self.selected_indexes = dict()  # Maps item type to selected indexes

    def build_tree(self):
        """Builds tree."""
        self.beginResetModel()
        self._invisible_root_item.deleteLater()
        self._invisible_root_item = TreeItem()
        self.selected_indexes.clear()
        self.endResetModel()
        self.track_item(self._invisible_root_item)
        self._root_item = self._create_root_item(self._db_map_data)
        self._invisible_root_item.insert_children(0, [self._root_item])

    def track_item(self, item):
        """Tracks given TreeItem. This means we insert rows when children are inserted
        and remove rows when children are removed."""
        item.children_about_to_be_inserted.connect(self._begin_insert_rows)
        item.children_inserted.connect(self._end_insert_rows)
        item.children_about_to_be_removed.connect(self._begin_remove_rows)
        item.children_removed.connect(self._end_remove_rows)

    def stop_tracking_item(self, item):
        """Stops tracking given TreeItem."""
        item.children_about_to_be_inserted.disconnect(self._begin_insert_rows)
        item.children_inserted.disconnect(self._end_insert_rows)
        item.children_about_to_be_removed.disconnect(self._begin_remove_rows)
        item.children_removed.disconnect(self._end_remove_rows)

    @Slot("QVariant", "int", "int", name="_begin_insert_rows")
    def _begin_insert_rows(self, item, row, count):
        """Begin an operation to insert rows."""
        index = self.index_from_item(item)
        self.beginInsertRows(index, row, row + count - 1)

    @Slot("QVariant", name="_end_insert_rows")
    def _end_insert_rows(self, items):
        """End an operation to insert rows. Start tracking all inserted items."""
        for item in items:
            self.track_item(item)
        self.endInsertRows()

    @Slot("QVariant", "int", "int", name="_begin_remove_rows")
    def _begin_remove_rows(self, item, row, count):
        """Begin an operation to remove rows."""
        index = self.index_from_item(item)
        self.beginRemoveRows(index, row, row + count - 1)

    @Slot("QVariant", name="_end_remove_rows")
    def _end_remove_rows(self, items):
        """End an operation to remove rows. Stop tracking all removed items."""
        for item in items:
            self.stop_tracking_item(item)
        self.endRemoveRows()

    @property
    def root_item(self):
        return self._root_item

    @property
    def root_index(self):
        return self.index_from_item(self._root_item)

    def _create_root_item(self):
        """Implement in subclasses to create a model specific to any entity type."""
        raise NotImplementedError()

    def visit_all(self, index=QModelIndex()):
        """Iterates all items in the model including and below the given index.
        Iterative implementation so we don't need to worry about Python recursion limits.
        """
        if index.isValid():
            ancient_one = self.item_from_index(index)
        else:
            ancient_one = self._invisible_root_item
        yield ancient_one
        child = ancient_one.last_child()
        if not child:
            return
        current = child
        visit_children = True
        while True:
            yield current
            if visit_children:
                child = current.last_child()
                if child:
                    current = child
                    continue
            sibling = current.previous_sibling()
            if sibling:
                visit_children = True
                current = sibling
                continue
            parent = current._parent
            if parent == ancient_one:
                break
            visit_children = False  # Make sure we don't visit children again
            current = parent

    def item_from_index(self, index):
        """Return the item corresponding to the given index."""
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self._invisible_root_item

    def index_from_item(self, item):
        """Return a model index corresponding to the given item."""
        return self.createIndex(item.child_number(), 0, item)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        item = self.item_from_index(index)
        parent_item = item.parent
        if parent_item == self._invisible_root_item:
            return QModelIndex()
        return self.createIndex(parent_item.child_number(), 0, parent_item)

    def data(self, index, role):
        item = self.item_from_index(index)
        if role == Qt.DecorationRole and index.column() == 0:
            return item.display_icon(self._parent.icon_mngr)
        return item.data(index.column(), role)

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        item = self.item_from_index(index)
        if role == Qt.EditRole:
            return item.set_data(index.column(), value)
        return False

    def flags(self, index):
        item = self.item_from_index(index)
        return item.flags(index.column())

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ("name", "database")[section]
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_item = self.item_from_index(parent)
        item = parent_item.child(row)
        if item:
            return self.createIndex(row, column, item)
        return QModelIndex()

    def columnCount(self, parent=QModelIndex()):
        return 2

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        parent_item = self.item_from_index(parent)
        return parent_item.child_count()

    def hasChildren(self, parent):
        parent_item = self.item_from_index(parent)
        return parent_item.has_children()

    def canFetchMore(self, parent):
        parent_item = self.item_from_index(parent)
        return parent_item.can_fetch_more()

    def fetchMore(self, parent):
        parent_item = self.item_from_index(parent)
        parent_item.fetch_more()

    def deselect_index(self, index):
        """Marks the index as deselected."""
        if not index.isValid() or index.column() != 0:
            return
        item_type = type(self.item_from_index(index))
        self.selected_indexes[item_type].pop(index)

    def select_index(self, index):
        """Marks the index as selected."""
        if not index.isValid() or index.column() != 0:
            return
        item_type = type(self.item_from_index(index))
        self.selected_indexes.setdefault(item_type, {})[index] = None

    def cascade_filter_nodes(self, *conds, parents=(), fetch=False, fetched_only=True):
        """Filter nodes in cascade by given condition starting from the list of parents:
        Root --> Children with first cond --> Children with second cond, etc.
        Returns the nodes at the lowest level attained.
        Optionally fetch the nodes where it passes.
        """
        if not parents:
            parents = [self.root_item]
        for cond in conds:
            parents = [child for parent in parents for child in parent.find_children(cond)]
            if fetch:
                for parent in parents:
                    index = self.index_from_item(parent)
                    self.canFetchMore(index) and self.fetchMore(index)
        if fetched_only:
            return [parent for parent in parents if not self.canFetchMore(self.index_from_item(parent))]
        return parents

    def cascade_filter_nodes_by_id(self, db_map, *ids_set, parents=(), fetch=False, fetched_only=True):
        """Filter nodes by ids in cascade starting from the list of parents:
        Root --> Children with id in the first set --> Children with id in the second set...
        Returns the nodes at the lowest level attained.
        Optionally fetch the nodes where it passes.
        """
        # TODO: maybe implement visit_all based on this?
        if not parents:
            parents = [self.root_item]
        for ids in ids_set:
            parents = [child for parent in parents for child in parent.find_children_by_id(db_map, *ids)]
            if fetch:
                for parent in parents:
                    index = self.index_from_item(parent)
                    self.canFetchMore(index) and self.fetchMore(index)
        if fetched_only:
            return [parent for parent in parents if not self.canFetchMore(self.index_from_item(parent))]
        return parents


class ObjectTreeModel(EntityTreeModel):
    """An 'object-oriented' tree model."""

    remove_icon = QIcon(":/icons/menu_icons/cube_minus.svg")

    @staticmethod
    def _create_root_item(db_map_data):
        return ObjectTreeRootItem(db_map_data)

    @property
    def selected_object_class_indexes(self):
        return self.selected_indexes.get(ObjectClassItem, {})

    @property
    def selected_object_indexes(self):
        return self.selected_indexes.get(ObjectItem, {})

    @property
    def selected_relationship_class_indexes(self):
        return self.selected_indexes.get(RelationshipClassItem, {})

    @property
    def selected_relationship_indexes(self):
        return self.selected_indexes.get(RelationshipItem, {})

    def _group_object_data(self, db_map_data):
        """Takes given object data and returns the same data keyed by parent tree-item.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, items in db_map_data.items():
            # Group items by class id
            d = dict()
            for item in items:
                d.setdefault(item["class_id"], []).append(item)
            for class_id, data in d.items():
                # Find the parents corresponding the this class id and put them in the result
                for parent in self.cascade_filter_nodes_by_id(db_map, (class_id,)):
                    result.setdefault(parent, {})[db_map] = data
        return result

    def _group_relationship_class_data(self, db_map_data):
        """Takes given relationship class data and returns the same data keyed by parent tree-item.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, items in db_map_data.items():
            d = dict()
            for item in items:
                for object_class_id in item["object_class_id_list"].split(","):
                    d.setdefault(int(object_class_id), []).append(item)
            for object_class_id, data in d.items():
                for parent in self.cascade_filter_nodes_by_id(db_map, (object_class_id,), (True,)):
                    result.setdefault(parent, {})[db_map] = data
        return result

    def _group_relationship_data(self, db_map_data):
        """Takes given relationship data and returns the same data keyed by parent tree-item.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, items in db_map_data.items():
            d = dict()
            for item in items:
                for object_id in item["object_id_list"].split(","):
                    key = (int(object_id), item["class_id"])
                    d.setdefault(key, []).append(item)
            for (object_id, class_id), data in d.items():
                for parent in self.cascade_filter_nodes_by_id(db_map, (True,), (object_id,), (class_id,)):
                    result.setdefault(parent, {})[db_map] = data
        return result

    def add_object_classes(self, db_map_data):
        selected_items = [self.item_from_index(ind) for ind in self.selected_object_class_indexes]
        self.root_item.append_children_from_data(db_map_data)
        self.selected_indexes[ObjectClassItem] = {self.index_from_item(item): None for item in selected_items}

    def add_objects(self, db_map_data):
        for parent, db_map_data in self._group_object_data(db_map_data).items():
            parent.append_children_from_data(db_map_data)

    def add_relationship_classes(self, db_map_data):
        for parent, db_map_data in self._group_relationship_class_data(db_map_data).items():
            parent.append_children_from_data(db_map_data)

    def add_relationships(self, db_map_data):
        for parent, db_map_data in self._group_relationship_data(db_map_data).items():
            parent.append_children_from_data(db_map_data)

    def remove_object_classes(self, db_map_data):
        # TODO: what happens with the selection here???
        self.root_item.remove_children_by_data(db_map_data)

    def remove_objects(self, db_map_data):
        for parent, db_map_data in self._group_object_data(db_map_data).items():
            parent.remove_children_by_data(db_map_data)

    def remove_relationship_classes(self, db_map_data):
        for parent, db_map_data in self._group_relationship_class_data(db_map_data).items():
            parent.remove_children_by_data(db_map_data)

    def remove_relationships(self, db_map_data):
        for parent, db_map_data in self._group_relationship_data(db_map_data).items():
            parent.remove_children_by_data(db_map_data)

    def update_object_classes(self, db_map_data):
        self.root_item.update_children_with_data(db_map_data)
        # TODO: update object class name in relationship class items

    def update_objects(self, db_map_data):
        for parent, db_map_data in self._group_object_data(db_map_data).items():
            parent.update_children_with_data(db_map_data)
        # TODO: update object name in relationship items

    def update_relationship_classes(self, db_map_data):
        for parent, db_map_data in self._group_relationship_class_data(db_map_data).items():
            parent.update_children_with_data(db_map_data)

    def update_relationships(self, db_map_data):
        for parent, db_map_data in self._group_relationship_data(db_map_data).items():
            parent.update_children_with_data(db_map_data)

    def find_next_relationship_index(self, index):
        """Find and return next ocurrence of relationship item."""
        # Mildly insane? But I can't think of something better now
        if not index.isValid():
            return
        rel_item = self.item_from_index(index)
        if not isinstance(rel_item, RelationshipItem):
            return
        # Get all ancestors
        rel_cls_item = rel_item._parent
        obj_item = rel_cls_item._parent
        obj_cls_item = obj_item._parent
        # Get data from ancestors
        # TODO: Is it enough to just use the first db_map?
        db_map = rel_item.first_db_map
        rel_data = rel_item.db_map_data(db_map)
        rel_cls_data = rel_cls_item.db_map_data(db_map)
        obj_data = obj_item.db_map_data(db_map)
        obj_cls_data = obj_cls_item.db_map_data(db_map)
        # Get specific data for our searches
        rel_cls_id = rel_cls_data['id']
        obj_id = obj_data['id']
        obj_cls_id = obj_cls_data['id']
        object_ids = list(reversed([int(id_) for id_ in rel_data['object_id_list'].split(",")]))
        object_class_ids = list(reversed([int(id_) for id_ in rel_cls_data['object_class_id_list'].split(",")]))
        # Find position in the relationship of the (grand parent) object,
        # then use it to determine object class and object id to look for
        pos = object_ids.index(obj_id) - 1
        object_id = object_ids[pos]
        object_class_id = object_class_ids[pos]
        # Return first node that passes all cascade fiters
        for parent in self.cascade_filter_nodes_by_id(
            db_map, (object_class_id,), (object_id,), (rel_cls_id,), fetch=True
        ):
            for item in parent.find_children(lambda child: child.display_id == rel_item.display_id):
                return self.index_from_item(item)
        return None


class RelationshipTreeModel(EntityTreeModel):
    """A relationship-oriented tree model."""

    remove_icon = QIcon(":/icons/menu_icons/cubes_minus.svg")

    @staticmethod
    def _create_root_item(db_map_data):
        return RelationshipTreeRootItem(db_map_data)

    @property
    def selected_relationship_class_indexes(self):
        return self.selected_indexes.get(RelationshipClassItem, {})

    @property
    def selected_relationship_indexes(self):
        return self.selected_indexes.get(RelationshipItem, {})

    def _mapped_relationship_class_data(self, db_map_data):
        """Takes given object class data and returns associated relationship class data.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, data in db_map_data.items():
            result[db_map] = self._map_object_class_to_relationship_class_data(db_map, data)
        return result

    def _map_object_class_to_relationship_class_data(self, db_map, data):
        """Finds relationship classes involving object classes in given data."""
        obj_cls_ids = {x["id"] for x in data}
        result = []
        for item in self.cascade_filter_nodes(
            lambda rel_cls: obj_cls_ids.intersection(
                rel_cls.db_map_data_field(db_map, "parsed_object_class_id_list", [])
            ),
            fetched_only=False,
        ):
            result.append(item.db_map_data(db_map))
        return result

    def _group_mapped_relationship_data(self, db_map_data):
        """Takes given object data and returns associated relationship data keyed by parent tree-item.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, items in db_map_data.items():
            d = dict()
            for item in items:
                d.setdefault(item["class_id"], []).append(item)
            for class_id, data in d.items():
                for parent in self.cascade_filter_nodes(
                    lambda rel_cls: class_id in rel_cls.db_map_data_field(db_map, "parsed_object_class_id_list", [])
                ):
                    object_ids = {x["id"] for x in data}
                    result.setdefault(parent, {})[db_map] = self._map_object_to_relationship_data(db_map, data, parent)
        return result

    def _map_object_to_relationship_data(self, db_map, data, parent):
        """Finds relationships under the given parent involving objects in given data."""
        object_ids = {x["id"] for x in data}
        result = []
        for item in self.cascade_filter_nodes(
            lambda rel: object_ids.intersection(
                rel.db_map_data_field(db_map, "parsed_object_id_list", []), parents=[parent]
            ),
            fetched_only=False,
        ):
            result.append(item.db_map_data(db_map))
        return result

    def _group_relationship_data(self, db_map_data):
        """Takes given relationship data and returns the same data keyed by parent tree-item.

        Args:
            db_map_data (dict): maps DiffDatabaseMapping instances to list of items as dict

        Returns:
            result (dict): maps parent tree-items to DiffDatabaseMapping instances to list of items as dict
        """
        result = dict()
        for db_map, items in db_map_data.items():
            d = dict()
            for item in items:
                d.setdefault(item["class_id"], []).append(item)
            for class_id, data in d.items():
                for parent in self.cascade_filter_nodes_by_id(db_map, (class_id,)):
                    result.setdefault(parent, {})[db_map] = data
        return result

    def add_relationship_classes(self, db_map_data):
        self.root_item.append_children_from_data(db_map_data)

    def add_relationships(self, db_map_data):
        for parent, db_map_data in self._group_relationship_data(db_map_data).items():
            parent.append_children_from_data(db_map_data)

    def remove_relationship_classes(self, db_map_data):
        self.root_item.remove_children_by_data(db_map_data)

    def remove_relationships(self, db_map_data):
        for parent, db_map_data in self._group_relationship_data(db_map_data).items():
            parent.remove_children_by_data(db_map_data)

    def remove_object_classes(self, db_map_data):
        db_map_data = self._mapped_relationship_class_data(db_map_data)
        self.root_item.remove_children_by_data(db_map_data)

    def remove_objects(self, db_map_data):
        for parent, db_map_data in self._group_mapped_relationship_data(db_map_data).items():
            parent.remove_children_by_data(db_map_data)
