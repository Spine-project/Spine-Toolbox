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
Classes for custom line edits.

:authors: M. Marin (KTH), P. Savolainen (VTT)
:date:   11.10.2018
"""

import os
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QLineEdit, QUndoStack
from PySide2.QtGui import QKeySequence


class PropertyQLineEdit(QLineEdit):
    """A custom QLineEdit for Project Item Properties."""

    def keyPressEvent(self, e):
        """Overridden to catch and pass on the
        Undo and Redo commands when this line
        edit has the focus.

        Args:
            e (QKeyEvent): Event
        """
        undo_stack = self.nativeParentWidget().findChild(QUndoStack)
        if undo_stack is None:
            super().keyPressEvent(e)
            return
        if e.matches(QKeySequence.Undo):
            undo_stack.undo()
        elif e.matches(QKeySequence.Redo):
            undo_stack.redo()
        else:
            super().keyPressEvent(e)

    def setText(self, text):
        """Overridden to prevent the cursor going to the end whenever the user is still editing.
        This happens because we set the text programmatically in undo/redo implementations.
        """
        pos = self.cursorPosition()
        super().setText(text)
        self.setCursorPosition(pos)


class CustomQLineEdit(PropertyQLineEdit):
    """A custom QLineEdit that accepts file drops and displays the path.

    Attributes:
        parent (QMainWindow): Parent for line edit widget
    """

    file_dropped = Signal("QString", name="file_dropped")

    def dragEnterEvent(self, event):
        """Accept a single file drop from the filesystem."""
        urls = event.mimeData().urls()
        if len(urls) > 1:
            event.ignore()
            return
        url = urls[0]
        if not url.isLocalFile():
            event.ignore()
            return
        if not os.path.isfile(url.toLocalFile()):
            event.ignore()
            return
        event.accept()
        event.setDropAction(Qt.LinkAction)

    def dragMoveEvent(self, event):
        """Accept event."""
        event.accept()

    def dropEvent(self, event):
        """Emit file_dropped signal with the file for the dropped url."""
        url = event.mimeData().urls()[0]
        self.file_dropped.emit(url.toLocalFile())
