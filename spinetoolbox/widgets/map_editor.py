######################################################################################################################
# Copyright (C) 2017-2020 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
An editor widget for editing a map type parameter values.

:author: A. Soininen (VTT)
:date:   11.2.2020
"""

from PySide2.QtCore import QModelIndex, QPoint, Qt, Slot
from PySide2.QtWidgets import QMenu, QWidget
from spinedb_api import Map
from .map_value_editor import MapValueEditor
from ..mvcmodels.map_model import MapModel
from ..spine_db_editor.widgets.custom_delegates import MapEditorTableDelegate


class MapEditor(QWidget):
    """
    A widget for editing maps.

    Attributes:
        parent (QWidget):
    """

    def __init__(self, parent=None):
        from ..ui.map_editor import Ui_MapEditor  # pylint: disable=import-outside-toplevel

        super().__init__(parent)
        self._model = MapModel(Map(["key"], [0.0]))
        self._ui = Ui_MapEditor()
        self._ui.setupUi(self)
        self._ui.map_table_view.setModel(self._model)
        self._ui.map_table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._ui.map_table_view.customContextMenuRequested.connect(self._show_table_context_menu)
        delegate = MapEditorTableDelegate(self._ui.map_table_view)
        delegate.value_editor_requested.connect(self._open_value_editor)
        self._ui.map_table_view.setItemDelegate(delegate)
        self._ui.convert_leaves_button.clicked.connect(self._convert_leaves)

    @Slot(bool)
    def _convert_leaves(self, _):
        self._model.convert_leaf_maps()

    @Slot(QPoint)
    def _show_table_context_menu(self, pos):
        menu = QMenu(self._ui.map_table_view)
        menu.addAction("Open value editor...")
        menu.addSeparator()
        menu.addAction("Insert row before")
        menu.addAction("Insert row after")
        menu.addAction("Remove row")
        menu.addSeparator()
        menu.addAction("Append column")
        menu.addAction("Trim columns")
        global_pos = self._ui.map_table_view.mapToGlobal(pos)
        action = menu.exec_(global_pos)
        if action is None:
            return
        action_text = action.text()
        selected_indexes = self._ui.map_table_view.selectedIndexes()
        selected_rows = sorted([index.row() for index in selected_indexes])
        first_row = selected_rows[0]
        if action_text == "Open value editor...":
            index = self._ui.map_table_view.indexAt(pos)
            self._open_value_editor(index)
        elif action_text == "Insert row before":
            self._model.insertRows(first_row, 1)
        elif action_text == "Insert row after":
            self._model.insertRows(first_row + 1, 1)
        elif action_text == "Remove row":
            self._model.removeRows(first_row, 1)
        elif action_text == "Append column":
            self._model.append_column()
        elif action_text == "Trim columns":
            self._model.trim_columns()

    def set_value(self, value):
        """Sets the parameter_value to be edited."""
        self._model.reset(value)

    def value(self):
        """Returns the parameter_value currently being edited."""
        return self._model.value()

    @Slot(QModelIndex)
    def _open_value_editor(self, index):
        """
        Opens value editor dialog for given map model index.

        Args:
            index (QModelIndex): index
        """
        editor = MapValueEditor(index, self)
        editor.show()
