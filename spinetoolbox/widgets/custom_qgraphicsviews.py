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
Classes for custom QGraphicsViews for the Design and Graph views.

:authors: P. Savolainen (VTT), M. Marin (KTH)
:date:   6.2.2018
"""

import logging
import math
from PySide2.QtWidgets import QGraphicsView
from PySide2.QtGui import QCursor
from PySide2.QtCore import Signal, Slot, Qt, QRectF, QTimeLine, QMarginsF
from ..graphics_items import LinkDrawer, Link
from .custom_qlistview import DragListView
from .custom_qgraphicsscene import CustomQGraphicsScene


class CustomQGraphicsView(QGraphicsView):
    """Super class for Design and Graph QGraphicsViews.

    Attributes:
        parent (QWidget): Parent widget
    """

    def __init__(self, parent):
        """Init CustomQGraphicsView."""
        super().__init__(parent=parent)
        self._zoom_factor_base = 1.0015
        self._angle = 120
        self._num_scheduled_scalings = 0
        self.anim = None
        self._scene_fitting_zoom = 1.0
        self._max_zoom = 10.0
        self._min_zoom = 0.1

    def keyPressEvent(self, event):
        """Overridden method. Enable zooming with plus and minus keys (comma resets zoom).
        Send event downstream to QGraphicsItems if pressed key is not handled here.

        Args:
            event (QKeyEvent): Pressed key
        """
        if event.key() == Qt.Key_Plus:
            self.zoom_in()
        elif event.key() == Qt.Key_Minus:
            self.zoom_out()
        elif event.key() == Qt.Key_Comma:
            self.reset_zoom()
        else:
            super().keyPressEvent(event)

    def enterEvent(self, event):
        """Overridden method. Do not show the stupid open hand mouse cursor.

        Args:
            event (QEvent): event
        """
        super().enterEvent(event)
        self.viewport().setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        """Set rubber band selection mode if Control pressed.
        Enable resetting the zoom factor from the middle mouse button.
        """
        if not self.itemAt(event.pos()):
            if event.modifiers() & Qt.ControlModifier:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                self.viewport().setCursor(Qt.CrossCursor)
            if event.button() == Qt.MidButton:
                self.reset_zoom()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Reestablish scroll hand drag mode."""
        super().mouseReleaseEvent(event)
        if not self.itemAt(event.pos()):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event):
        """Zoom in/out.

        Args:
            event (QWheelEvent): Mouse wheel event
        """
        if event.orientation() != Qt.Vertical:
            event.ignore()
            return
        event.accept()
        ui = self.parent().parent()
        qsettings = ui.qsettings()
        smooth_zoom = qsettings.value("appSettings/smoothZoom", defaultValue="false")
        if smooth_zoom == "true":
            num_degrees = event.delta() / 8
            num_steps = num_degrees / 15
            self._num_scheduled_scalings += num_steps
            if self._num_scheduled_scalings * num_steps < 0:
                self._num_scheduled_scalings = num_steps
            if self.anim:
                self.anim.deleteLater()
            self.anim = QTimeLine(200, self)
            self.anim.setUpdateInterval(20)
            self.anim.valueChanged.connect(lambda x, pos=event.pos(): self.scaling_time(pos))
            self.anim.finished.connect(self.anim_finished)
            self.anim.start()
        else:
            angle = event.angleDelta().y()
            factor = self._zoom_factor_base ** angle
            self.gentle_zoom(factor, event.pos())

    def resizeEvent(self, event):
        """
        Updates zoom if needed when the view is resized.

        Args:
            event (QResizeEvent): a resize event
        """
        new_size = self.size()
        old_size = event.oldSize()
        if new_size != old_size:
            scene = self.scene()
            if scene is not None:
                self._update_zoom_limits(scene.sceneRect())
                if new_size.width() > old_size.width() or new_size.height() > old_size.height():
                    transform = self.transform()
                    zoom = transform.m11()
                    if zoom < self._min_zoom:
                        # Reset the zoom if the view has grown and the current zoom is too small
                        self.reset_zoom()
        super().resizeEvent(event)

    def setScene(self, scene):
        """
        Sets a new scene to this view.

        Args:
            scene (QGraphicsScene): a new scene
        """
        super().setScene(scene)
        scene.sceneRectChanged.connect(self._update_zoom_limits)

    @Slot("QRectF", name="_update_zoom_limits")
    def _update_zoom_limits(self, rect):
        """
        Updates the minimum zoom limit and the zoom level with which the entire scene fits the view.

        Args:
            rect (QRectF): the scene's rect
        """
        scene_extent = max(rect.width(), rect.height())
        if not scene_extent:
            return
        size = self.size()
        extent = min(size.height(), size.width())
        self._scene_fitting_zoom = extent / scene_extent
        self._min_zoom = min(self._scene_fitting_zoom, 0.1)

    def scaling_time(self, pos):
        """Called when animation value for smooth zoom changes. Perform zoom."""
        factor = 1.0 + self._num_scheduled_scalings / 100.0
        self.gentle_zoom(factor, pos)

    def anim_finished(self):
        """Called when animation for smooth zoom finishes. Clean up."""
        if self._num_scheduled_scalings > 0:
            self._num_scheduled_scalings -= 1
        else:
            self._num_scheduled_scalings += 1
        self.sender().deleteLater()
        self.anim = None

    def zoom_in(self):
        """Perform a zoom in with a fixed scaling."""
        self.gentle_zoom(self._zoom_factor_base ** self._angle, self.viewport().rect().center())

    def zoom_out(self):
        """Perform a zoom out with a fixed scaling."""
        self.gentle_zoom(self._zoom_factor_base ** -self._angle, self.viewport().rect().center())

    def reset_zoom(self):
        """Reset zoom to the default factor."""
        self.resetTransform()
        if self._scene_fitting_zoom < 1.0:
            self.scale(self._scene_fitting_zoom, self._scene_fitting_zoom)

    def gentle_zoom(self, factor, zoom_focus):
        """
        Perform a zoom by a given factor.

        Args:
            factor (float): a scaling factor relative to the current scene scaling
            zoom_focus (QPoint): focus of the zoom, e.g. mouse pointer position
        """
        initial_focus_on_scene = self.mapToScene(zoom_focus)
        transform = self.transform()
        current_zoom = transform.m11()  # The [1, 1] element contains the x scaling factor
        proposed_zoom = current_zoom * factor
        if proposed_zoom < self._min_zoom:
            factor = self._min_zoom / current_zoom
        elif proposed_zoom > self._max_zoom:
            factor = self._max_zoom / current_zoom
        if math.isclose(factor, 1.0):
            return False
        self.scale(factor, factor)
        post_scaling_focus_on_scene = self.mapToScene(zoom_focus)
        center_on_scene = self.mapToScene(self.viewport().rect().center())
        focus_diff = post_scaling_focus_on_scene - initial_focus_on_scene
        self.centerOn(center_on_scene - focus_diff)
        return True


class DesignQGraphicsView(CustomQGraphicsView):
    """QGraphicsView for the Design View.

    Attributes:
        parent (QWidget): Graph View Form's (QMainWindow) central widget (self.centralwidget)
    """

    def __init__(self, parent):
        """Initialize DesignQGraphicsView."""
        super().__init__(parent=parent)  # Parent is passed to QWidget's constructor
        self._scene = None
        self._toolbox = None
        self._project_item_model = None
        self.link_drawer = None
        self.src_connector = None  # Source connector of a link drawing operation
        self.dst_connector = None  # Destination connector of a link drawing operation
        self.src_item_name = None  # Name of source project item when drawing links
        self.dst_item_name = None  # Name of destination project item when drawing links

    def mousePressEvent(self, event):
        """Manage drawing of links. Handle the case where a link is being
        drawn and the user doesn't hit a connector button.

        Args:
            event (QGraphicsSceneMouseEvent): Mouse event
        """
        was_drawing = self.link_drawer.drawing if self.link_drawer else None
        # This below will trigger connector button if any
        super().mousePressEvent(event)
        if was_drawing:
            self.link_drawer.hide()
            # If `drawing` is still `True` here, it means we didn't hit a connector
            if self.link_drawer.drawing:
                self.link_drawer.drawing = False
                if event.button() != Qt.LeftButton:
                    return
                self._toolbox.msg_warning.emit(
                    "Unable to make connection. Try landing the connection onto a connector button."
                )

    def mouseMoveEvent(self, event):
        """Update line end position.

        Args:
            event (QGraphicsSceneMouseEvent): Mouse event
        """
        if self.link_drawer and self.link_drawer.drawing:
            self.link_drawer.dst = self.mapToScene(event.pos())
            self.link_drawer.update_geometry()
        super().mouseMoveEvent(event)

    def set_ui(self, toolbox):
        """Set a new scene into the Design View when app is started."""
        self._toolbox = toolbox
        self.setScene(CustomQGraphicsScene(self, toolbox))

    def init_scene(self, empty=False):
        """Resize scene and add a link drawer on scene.
        The scene must be cleared before calling this.

        Args:
            empty (boolean): True when creating a new project
        """
        self.link_drawer = LinkDrawer()
        self.scene().addItem(self.link_drawer)
        if len(self.scene().items()) == 1:
            # Loaded project has no project items
            empty = True
        if not empty:
            # Reset scene rectangle to be as big as the items bounding rectangle
            items_rect = self.scene().itemsBoundingRect()
            margin_rect = items_rect.marginsAdded(QMarginsF(20, 20, 20, 20))  # Add margins
            self.scene().setSceneRect(margin_rect)
        else:
            rect = QRectF(0, 0, 401, 301)
            self.scene().setSceneRect(rect)
        self.scene().update()
        self.reset_zoom()

    def set_project_item_model(self, model):
        """Set project item model."""
        self._project_item_model = model

    def remove_icon(self, icon):
        """Removes icon and all connected links from scene."""
        links = set(link for conn in icon.connectors.values() for link in conn.links)
        for link in links:
            self.scene().removeItem(link)
            # Remove Link from connectors
            link.src_connector.links.remove(link)
            link.dst_connector.links.remove(link)
        scene = self.scene()
        scene.removeItem(icon)
        scene.shrink_if_needed()

    def links(self):
        """Returns all Links in the scene.
        Used for saving the project."""
        return [item for item in self.items() if isinstance(item, Link)]

    def add_link(self, src_connector, dst_connector):
        """Draws link between source and destination connectors on scene.

        Args:
            src_connector (ConnectorButton): Source connector button
            dst_connector (ConnectorButton): Destination connector button
        """
        link = Link(self._toolbox, src_connector, dst_connector)
        self.scene().addItem(link)
        # Store Link in connectors, so it can be found *from* the Project Item
        src_connector.links.append(link)
        dst_connector.links.append(link)
        # Add edge (connection link) to a dag as well
        src_name = link.src_icon.name()
        dst_name = link.dst_icon.name()
        self._toolbox.project().dag_handler.add_graph_edge(src_name, dst_name)

    def remove_link(self, link, from_dag=True):
        """Removes link from scene."""
        self.scene().removeItem(link)
        # Remove Link from connectors
        link.src_connector.links.remove(link)
        link.dst_connector.links.remove(link)
        # Remove edge (connection link) from dag
        src_name = link.src_icon.name()
        dst_name = link.dst_icon.name()
        self._toolbox.project().dag_handler.remove_graph_edge(src_name, dst_name)

    def take_link(self, link):
        """Remove link, then start drawing another one from the same source connector."""
        self.remove_link(link)
        self.draw_links(link.src_connector)
        # noinspection PyArgumentList
        self.link_drawer.dst = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        self.link_drawer.update_geometry()

    def restore_links(self, connections):
        """Creates Links from the given connections list.
        Two formats are accepted.

        - Old format. List of lists, e.g.

        .. code-block::

            [
                [False, False, ["right", "left"], False],
                [False, ["bottom", "left"], False, False],
                ...
            ]

        - New format. List of dicts, e.g.

        .. code-block::

            [
                {"from": ["DC1", "right"], "to": ["Tool1", "left"]},
                ...
            ]

        Args:
            connections (list): list of connections.
        """
        if not connections:
            return
        # Convert old format to new format
        if isinstance(connections[0], list):
            connections_old = connections.copy()
            connections.clear()
            items = self._project_item_model.items()
            for i, row in enumerate(connections_old):
                for j, entry in enumerate(row):
                    if entry is False:
                        continue
                    try:
                        src_item = items[i]
                        dst_item = items[j]
                    except IndexError:
                        # Might happen when e.g. the project file contains project items
                        # that couldn't be restored because the corresponding project item plugin wasn't found
                        self._toolbox.msg_warning.emit("Restoring a connection failed")
                        continue
                    try:
                        src_anchor, dst_anchor = entry
                    except TypeError:
                        # Happens when first loading a project that wasn't saved with the current version
                        src_anchor = dst_anchor = "bottom"
                    entry_new = {"from": [src_item.name, src_anchor], "to": [dst_item.name, dst_anchor]}
                    connections.append(entry_new)
        # Now just assume new format
        for conn in connections:
            src_name, src_anchor = conn["from"]
            dst_name, dst_anchor = conn["to"]
            src_ind = self._project_item_model.find_item(src_name)
            dst_ind = self._project_item_model.find_item(dst_name)
            if not src_ind or not dst_ind:
                self._toolbox.msg_warning.emit("Restoring a connection failed")
                continue
            src_item = self._project_item_model.project_item(src_ind)
            src_connector = src_item.get_icon().conn_button(src_anchor)
            dst_item = self._project_item_model.project_item(dst_ind)
            dst_connector = dst_item.get_icon().conn_button(dst_anchor)
            self.add_link(src_connector, dst_connector)

    def draw_links(self, connector):
        """Draw links when slot button is clicked.

        Args:
            connector (ConnectorButton): Connector button that triggered the drawing
        """
        if not self.link_drawer.drawing:
            # start drawing and remember source connector
            self.link_drawer.drawing = True
            self.link_drawer.start_drawing_at(connector.sceneBoundingRect())
            self.src_connector = connector
        else:
            # stop drawing and make connection
            self.link_drawer.drawing = False
            self.dst_connector = connector
            self.src_item_name = self.src_connector.parent_name()
            self.dst_item_name = self.dst_connector.parent_name()
            # create connection
            self.add_link(self.src_connector, self.dst_connector)
            self.notify_destination_items()

    def notify_destination_items(self):
        """Notify destination items that they have been connected to a source item."""
        if self.src_item_name == self.dst_item_name:
            self._toolbox.msg_warning.emit("Link established. Feedback link functionality not implemented.")
        else:
            src_index = self._project_item_model.find_item(self.src_item_name)
            if not src_index:
                logging.error("Item %s not found", self.src_item_name)
                return
            dst_index = self._project_item_model.find_item(self.dst_item_name)
            if not dst_index:
                logging.error("Item %s not found", self.dst_item_name)
                return
            src_item = self._project_item_model.project_item(src_index)
            dst_item = self._project_item_model.project_item(dst_index)
            dst_item.notify_destination(src_item)


class GraphQGraphicsView(CustomQGraphicsView):
    """QGraphicsView for the Graph View."""

    item_dropped = Signal("QPoint", "QString", name="item_dropped")

    def __init__(self, parent):
        """Init GraphQGraphicsView."""
        super().__init__(parent=parent)
        self._graph_view_form = None

    def set_graph_view_form(self, form):
        """Sets the _graph_view_form attribute."""
        self._graph_view_form = form

    def dragLeaveEvent(self, event):
        """Accept event. Then call the super class method
        only if drag source is not DragListView."""
        event.accept()

    def dragEnterEvent(self, event):
        """Accept event. Then call the super class method
        only if drag source is not DragListView."""
        event.accept()
        source = event.source()
        if not isinstance(source, DragListView):
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """Accept event. Then call the super class method
        only if drag source is not DragListView."""
        event.accept()
        source = event.source()
        if not isinstance(source, DragListView):
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """Only accept drops when the source is an instance of DragListView.
        Capture text from event's mimedata and emit signal.
        """
        source = event.source()
        if not isinstance(source, DragListView):
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        text = event.mimeData().text()
        pos = event.pos()
        self.item_dropped.emit(pos, text)

    def contextMenuEvent(self, e):
        """Show context menu.

        Args:
            e (QContextMenuEvent): Context menu event
        """
        super().contextMenuEvent(e)
        if e.isAccepted():
            return
        if not self._graph_view_form:
            e.ignore()
            return
        e.accept()
        self._graph_view_form.show_graph_view_context_menu(e.globalPos())

    def gentle_zoom(self, factor, zoom_focus):
        """
        Perform a zoom by a given factor.

        Args:
            factor (float): a scaling factor relative to the current scene scaling
            zoom_focus (QPoint): focus of the zoom, e.g. mouse pointer position
        """
        if not super().gentle_zoom(factor, zoom_focus):
            return False
        self.adjust_items_to_zoom(factor)
        return True

    def reset_zoom(self):
        """Reset zoom to the default factor."""
        self.resetTransform()
        self.reset_items_zoom()
        self.init_zoom()

    def init_zoom(self):
        """Init zoom."""
        self.resetTransform()
        self.scale(self._scene_fitting_zoom, self._scene_fitting_zoom)
        self.adjust_items_to_zoom(self._scene_fitting_zoom)

    def adjust_items_to_zoom(self, factor):
        """Update items geometry after performing a zoom.
        This is so items stay the same size (that is, the zoom controls the *spread*).

        Args:
            factor (float): a scaling factor relative to the current scene scaling
        """
        for item in self.items():
            try:
                item.adjust_to_zoom(factor)
            except AttributeError:
                pass

    def reset_items_zoom(self):
        """Reset items geometry to original unzoomed state.
        """
        for item in self.items():
            try:
                item.reset_zoom()
            except AttributeError:
                pass
