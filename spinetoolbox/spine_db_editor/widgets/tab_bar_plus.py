######################################################################################################################
# Copyright (C) 2017-2021 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Classes for custom context menus and pop-up menus.

:author: M. Marin (KTH)
:date:   13.5.2020
"""
from PySide2.QtWidgets import QTabBar, QToolButton, QApplication, QMenu
from PySide2.QtCore import Signal, Qt, QEvent, QPoint
from PySide2.QtGui import QIcon, QMouseEvent, QCursor
from spinetoolbox.helpers import CharIconEngine


class TabBarPlus(QTabBar):
    """Tab bar that has a plus button floating to the right of the tabs."""

    plus_clicked = Signal()

    def __init__(self, parent):
        """
        Args:
            parent (MultiSpineDBEditor)
        """
        super().__init__(parent)
        self._parent = parent
        self._plus_button = QToolButton(self)
        self._plus_button.setIcon(QIcon(CharIconEngine("\uf067")))
        self._plus_button.clicked.connect(lambda _=False: self.plus_clicked.emit())
        self._move_plus_button()
        self.setShape(QTabBar.RoundedNorth)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setElideMode(Qt.ElideLeft)
        self.drag_index = None
        self._tab_hot_spot_x = None
        self._hot_spot_y = None

    def resizeEvent(self, event):
        """Sets the dimension of the plus button. Also, makes the tab bar as wide as the parent."""
        super().resizeEvent(event)
        self.setFixedWidth(self.parent().width())
        self.setMinimumHeight(self.height())
        self._move_plus_button()
        extent = max(0, self.height() - 2)
        self._plus_button.setFixedSize(extent, extent)
        self.setExpanding(False)

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self._move_plus_button()

    def _move_plus_button(self):
        """Places the plus button at the right of the last tab."""
        left = sum([self.tabRect(i).width() for i in range(self.count())])
        top = self.geometry().top() + 1
        self._plus_button.move(left, top)

    def mousePressEvent(self, event):
        """Registers the position of the press, in case we need to detach the tab."""
        super().mousePressEvent(event)
        tab_rect = self.tabRect(self.tabAt(event.pos()))
        self._tab_hot_spot_x = event.pos().x() - tab_rect.x()
        self._hot_spot_y = event.pos().y() - tab_rect.y()

    def mouseMoveEvent(self, event):
        """Detaches a tab either if the user moves beyond the limits of the tab bar, or if it's the only one."""
        self._plus_button.hide()
        if self.count() == 1:
            self._send_release_event(event.pos())
            hot_spot = QPoint(event.pos().x(), self._hot_spot_y)
            self._parent.start_drag(hot_spot)
            return
        if self.count() > 1 and not self.geometry().contains(event.pos()):
            self._send_release_event(event.pos())
            hot_spot_x = event.pos().x()
            hot_spot = QPoint(event.pos().x(), self._hot_spot_y)
            index = self.tabAt(hot_spot)
            if index == -1:
                index = self.count() - 1
            self._parent.detach(index, hot_spot, hot_spot_x - self._tab_hot_spot_x)
            return
        super().mouseMoveEvent(event)

    def _send_release_event(self, pos):
        """Sends a mouse release event at given position in local coordinates. Called just before detaching a tab.

        Args:
            pos (QPoint)
        """
        self.drag_index = None
        release_event = QMouseEvent(QEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, release_event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._plus_button.show()
        self.update()
        self.releaseMouse()
        if self.drag_index is not None:
            # Pass it to parent
            event.ignore()

    def start_dragging(self, index):
        """Stars dragging the given index. This happens when a detached tab is reattached to this bar.

        Args:
            index (int)
        """
        self.drag_index = index
        press_pos = self.tabRect(self.drag_index).center()
        press_event = QMouseEvent(QEvent.MouseButtonPress, press_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, press_event)
        QApplication.processEvents()
        move_pos = self.mapFromGlobal(QCursor.pos())
        if self.geometry().contains(move_pos):
            move_event = QMouseEvent(QEvent.MouseMove, move_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            QApplication.sendEvent(self, move_event)
        self.grabMouse()

    def index_under_mouse(self):
        """Returns the index under the mouse cursor, or None if the cursor isn't over the tab bar.
        Used to check for drop targets.

        Returns:
            int or NoneType
        """
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.geometry().contains(pos):
            return None
        index = self.tabAt(pos)
        if index == -1:
            index = self.count()
        return index

    def _show_plus_button_context_menu(self, global_pos):
        toolbox = self._parent.db_mngr.parent()
        if toolbox is None:
            return
        ds_urls = {ds.name: ds.project_item.sql_alchemy_url() for ds in toolbox.project_item_model.items("Data Stores")}
        if not ds_urls:
            return
        menu = QMenu(self)
        for name, url in ds_urls.items():
            action = menu.addAction(name, lambda name=name, url=url: self._parent.add_new_tab({url: name}))
            action.setEnabled(bool(url))
        menu.popup(global_pos)
        menu.aboutToHide.connect(menu.deleteLater)

    def contextMenuEvent(self, event):
        index = self.tabAt(event.pos())
        if self._plus_button.underMouse():
            self._show_plus_button_context_menu(event.globalPos())
            return
        if self.tabButton(index, QTabBar.RightSide).underMouse():
            return
        db_editor = self._parent.tab_widget.widget(index)
        if db_editor is None:
            return
        menu = QMenu(self)
        others = self._parent.others()
        if others:
            move_tab_menu = menu.addMenu("Move tab to another window")
            move_tab_to_new_window = move_tab_menu.addAction(
                "New window", lambda _=False, index=index: self._parent.move_tab(index, None)
            )
            for other in others:
                move_tab_menu.addAction(
                    other.name(), lambda _=False, index=index, other=other: self._parent.move_tab(index, other)
                )
        else:
            move_tab_to_new_window = menu.addAction(
                "Move tab to new window", lambda _=False, index=index: self._parent.move_tab(index, None)
            )
        move_tab_to_new_window.setEnabled(self.count() > 1)
        menu.addSeparator()
        menu.addAction(db_editor.url_toolbar.reload_action)
        db_url_codenames = db_editor.db_url_codenames
        menu.addAction(
            QIcon(CharIconEngine("\uf24d")),
            "Duplicate",
            lambda _=False, index=index + 1, db_url_codenames=db_url_codenames: self._parent.insert_new_tab(
                index, db_url_codenames
            ),
        )
        menu.popup(event.globalPos())
        menu.aboutToHide.connect(menu.deleteLater)
        event.accept()
