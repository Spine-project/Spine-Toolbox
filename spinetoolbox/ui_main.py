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
Contains ToolboxUI class.

:author: P. Savolainen (VTT)
:date:   14.12.2017
"""

import os
import locale
import logging
import json
import numpy as np
from PySide2.QtCore import QByteArray, QMimeData, Qt, Signal, Slot, QSettings, QUrl, SIGNAL
from PySide2.QtGui import QCursor
from PySide2.QtWidgets import (
    QMainWindow,
    QApplication,
    QFileDialog,
    QMessageBox,
    QCheckBox,
    QInputDialog,
    QDockWidget,
    QAction,
)
from PySide2.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QStandardItemModel, QIcon
from .graphics_items import ProjectItemIcon
from .mvcmodels.project_item_model import ProjectItemModel
from .mvcmodels.tool_specification_model import ToolSpecificationModel
from .widgets.about_widget import AboutWidget
from .widgets.custom_menus import (
    ProjectItemModelContextMenu,
    ToolSpecificationContextMenu,
    LinkContextMenu,
    AddToolSpecificationPopupMenu,
    RecentProjectsPopupMenu,
)
from .widgets.project_form_widget import NewProjectForm
from .widgets.settings_widget import SettingsWidget
from .widgets.tool_configuration_assistant_widget import ToolConfigurationAssistantWidget
from .widgets.tool_specification_widget import ToolSpecificationWidget
from .widgets.custom_qwidgets import ZoomWidgetAction
from .widgets.julia_repl_widget import JuliaREPLWidget
from .widgets.python_repl_widget import PythonReplWidget
from .widgets import toolbars
from .project import SpineToolboxProject
from .config import STATUSBAR_SS, TEXTBROWSER_SS, MAINWINDOW_SS, DOCUMENTATION_PATH
from .helpers import project_dir, get_datetime, erase_dir, busy_effect, set_taskbar_icon, supported_img_formats
from .project_tree_item import CategoryProjectTreeItem, LeafProjectTreeItem, RootProjectTreeItem
from .project_items import data_store, data_connection, exporter, tool, view, importer


class ToolboxUI(QMainWindow):
    """Class for application main GUI functions."""

    # Signals to comply with the spinetoolbox.spine_logger.LoggingSignals interface.
    msg = Signal(str)
    msg_success = Signal(str)
    msg_error = Signal(str)
    msg_warning = Signal(str)
    dialog = Signal(str)
    # The rest of the msg_* signals should be moved to LoggingSignals in the long run.
    msg_proc = Signal(str)
    msg_proc_error = Signal(str)
    tool_specification_model_changed = Signal("QVariant")

    def __init__(self):
        """ Initialize application and main window."""
        from .ui.mainwindow import Ui_MainWindow

        super().__init__(flags=Qt.Window)
        self._qsettings = QSettings("SpineProject", "Spine Toolbox")
        # Set number formatting to use user's default settings
        locale.setlocale(locale.LC_NUMERIC, 'C')
        # Setup the user interface from Qt Designer files
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowIcon(QIcon(":/symbols/app.ico"))
        set_taskbar_icon()  # in helpers.py
        self.ui.graphicsView.set_ui(self)
        self._project_item_actions = list()
        self._item_edit_actions()
        # Set style sheets
        self.ui.statusbar.setStyleSheet(STATUSBAR_SS)  # Initialize QStatusBar
        self.ui.statusbar.setFixedHeight(20)
        self.ui.textBrowser_eventlog.setStyleSheet(TEXTBROWSER_SS)
        self.ui.textBrowser_process_output.setStyleSheet(TEXTBROWSER_SS)
        self.setStyleSheet(MAINWINDOW_SS)
        # Class variables
        self.categories = dict()  # Holds category data parsed from project item plugins
        self._project = None
        self.project_item_model = None
        self.tool_specification_model = None
        self.show_datetime = self.update_datetime()
        self.active_project_item = None
        # Widget and form references
        self.settings_form = None
        self.tool_specification_context_menu = None
        self.project_item_context_menu = None
        self.link_context_menu = None
        self.process_output_context_menu = None
        self.project_form = None
        self.add_project_item_form = None
        self.tool_specification_form = None
        self.placing_item = ""
        self.add_tool_specification_popup_menu = None
        self.zoom_widget_action = None
        self.recent_projects_menu = RecentProjectsPopupMenu(self)
        # Make and initialize toolbars
        self.item_toolbar = toolbars.ItemToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, self.item_toolbar)
        # Make julia REPL
        self.julia_repl = JuliaREPLWidget(self)
        self.ui.dockWidgetContents_julia_repl.layout().addWidget(self.julia_repl)
        # Make Python REPL
        self.python_repl = PythonReplWidget(self)
        self.ui.dockWidgetContents_python_repl.layout().addWidget(self.python_repl)
        # Setup main window menu
        self.setup_zoom_widget_action()
        self.add_toggle_view_actions()
        # Hidden QActions for debugging or testing
        self.show_properties_tabbar = QAction(self)
        self.show_supported_img_formats = QAction(self)
        self.test_variable_push = QAction(self)
        self.set_debug_qactions()
        self.ui.tabWidget_item_properties.tabBar().hide()  # Hide tab bar in properties dock widget
        # Finalize init
        self._proposed_item_name_counts = dict()
        self.connect_signals()
        self.restore_ui()
        self.parse_project_item_modules()

    # noinspection PyArgumentList, PyUnresolvedReferences
    def connect_signals(self):
        """Connect signals."""
        # Event log signals
        self.msg.connect(self.add_message)
        self.msg_success.connect(self.add_success_message)
        self.msg_error.connect(self.add_error_message)
        self.msg_warning.connect(self.add_warning_message)
        self.msg_proc.connect(self.add_process_message)
        self.msg_proc_error.connect(self.add_process_error_message)
        # Message box signals
        self.dialog.connect(self._show_message_box)
        # Menu commands
        self.ui.actionNew.triggered.connect(self.new_project)
        self.ui.actionOpen.triggered.connect(self.open_project)
        self.ui.actionOpen_recent.setMenu(self.recent_projects_menu)
        self.ui.actionOpen_recent.hovered.connect(self.show_recent_projects_menu)
        self.ui.actionSave.triggered.connect(self.save_project)
        self.ui.actionSave_As.triggered.connect(self.save_project_as)
        self.ui.actionExport_project_to_GraphML.triggered.connect(self.export_as_graphml)
        self.ui.actionSettings.triggered.connect(self.show_settings)
        self.ui.actionPackages.triggered.connect(self.show_tool_config_asst)
        self.ui.actionQuit.triggered.connect(self.close)
        self.ui.actionRemove_all.triggered.connect(self.remove_all_items)
        self.ui.actionUser_Guide.triggered.connect(self.show_user_guide)
        self.ui.actionGetting_started.triggered.connect(self.show_getting_started_guide)
        self.ui.actionAbout.triggered.connect(self.show_about)
        self.ui.actionAbout_Qt.triggered.connect(lambda: QApplication.aboutQt())  # pylint: disable=unnecessary-lambda
        self.ui.actionRestore_Dock_Widgets.triggered.connect(self.restore_dock_widgets)
        self.ui.actionCopy.triggered.connect(self.project_item_to_clipboard)
        self.ui.actionPaste.triggered.connect(self.project_item_from_clipboard)
        self.ui.actionDuplicate.triggered.connect(self.duplicate_project_item)
        # Debug QActions
        self.show_properties_tabbar.triggered.connect(self.toggle_properties_tabbar_visibility)
        self.show_supported_img_formats.triggered.connect(supported_img_formats)  # in helpers.py
        self.test_variable_push.triggered.connect(self.python_repl.test_push_vars)
        # Tool specifications tab
        self.add_tool_specification_popup_menu = AddToolSpecificationPopupMenu(self)
        self.ui.toolButton_add_tool_specification.setMenu(self.add_tool_specification_popup_menu)
        self.ui.toolButton_remove_tool_specification.clicked.connect(self.remove_selected_tool_specification)
        # Event Log & Process output
        self.ui.textBrowser_eventlog.anchorClicked.connect(self.open_anchor)
        # Context-menus
        self.ui.treeView_project.customContextMenuRequested.connect(self.show_item_context_menu)
        # Main menu
        self.zoom_widget_action.minus_pressed.connect(self._handle_zoom_minus_pressed)
        self.zoom_widget_action.plus_pressed.connect(self._handle_zoom_plus_pressed)
        self.zoom_widget_action.reset_pressed.connect(self._handle_zoom_reset_pressed)

    def parse_project_item_modules(self):
        """Collects attributes from project item modules into a dict.
        This dict is then used to perform all project item related tasks.
        """
        self.categories.clear()
        for module in (data_store, data_connection, tool, view, importer, exporter):
            item_rank = module.item_rank
            item_category = module.item_category
            item_type = module.item_type
            item_icon = module.item_icon
            item_maker = module.item_maker
            icon_maker = module.icon_maker
            add_form_maker = module.add_form_maker
            properties_widget = module.properties_widget_maker(self)
            properties_ui = properties_widget.ui
            self.categories[item_category] = dict(
                item_rank=item_rank,
                item_type=item_type,
                item_icon=item_icon,
                item_maker=item_maker,
                icon_maker=icon_maker,
                add_form_maker=add_form_maker,
                properties_ui=properties_ui,
            )
        # Sort categories by rank
        self.categories = dict(sorted(self.categories.items(), key=lambda kv: kv[1]["item_rank"]))
        # Create actions for Edit menu, and draggable widgets to toolbar
        category_icon = list()
        for item_category, item_dict in self.categories.items():
            item_icon = item_dict["item_icon"]
            item_type = item_dict["item_type"]
            category_icon.append((item_type, item_category, item_icon))
        # Add draggable widgets to toolbar
        self.item_toolbar.add_draggable_widgets(category_icon)

    def project(self):
        """Returns current project or None if no project open."""
        return self._project

    def qsettings(self):
        """Returns application preferences object."""
        return self._qsettings

    @Slot(name="init_project")
    def init_project(self, project_file_path):
        """
        Initializes project at application start-up.

        Loads the project stored in the given project_path.
        If the path is empty, loads the last project that was open  when app was closed
        or starts without a project if app is started for the first time.
        """
        if not project_file_path:
            open_previous_project = int(self._qsettings.value("appSettings/openPreviousProject", defaultValue="0"))
            if open_previous_project != Qt.Checked:
                p = os.path.join(DOCUMENTATION_PATH, "getting_started.html")
                getting_started_anchor = (
                    "<a style='color:#99CCFF;' title='" + p + "' href='file:///" + p + "'>Getting Started</a>"
                )
                self.msg.emit(
                    "Welcome to Spine Toolbox! If you need help, please read the {0} guide.".format(getting_started_anchor)
                )
                return
            # Get path to previous project file
            project_file_path = self._qsettings.value("appSettings/previousProject", defaultValue="")
            if not project_file_path:
                return
        if not os.path.isfile(project_file_path):
            msg = "Could not load previous project. File '{0}' not found.".format(project_file_path)
            self.ui.statusbar.showMessage(msg, 10000)
            return
        if not self.open_project(project_file_path, clear_event_log=False):
            self.msg_error.emit("Loading project file <b>{0}</b> failed".format(project_file_path))

    @Slot(name="new_project")
    def new_project(self):
        """Shows new project form."""
        self.project_form = NewProjectForm(self)
        self.project_form.show()

    def create_project(self, name, description):
        """Create new project and set it active.

        Args:
            name (str): Project name
            description (str): Project description
        """
        self.clear_ui()
        self._project = SpineToolboxProject(self, name, description)
        self._project.connect_signals()
        self.init_models(tool_specification_paths=list())  # Start project with no tool specifications
        self.setWindowTitle("Spine Toolbox    -- {} --".format(self._project.name))
        self.ui.graphicsView.init_scene(empty=True)
        self.update_recent_projects()
        self.msg.emit("New project created")
        self.save_project()

    # noinspection PyUnusedLocal
    @Slot(name="open_project")
    def open_project(self, load_path=None, clear_event_log=True):
        """Load project from a save file (.proj) file.

        Args:
            load_path (str): Path to project save file. If default value is used,
            a file explorer dialog is opened where the user can select the
            project file to load.
            clear_event_log (bool): True clears Event Log, False does not

        Returns:
            bool: True when opening the project succeeded, False otherwise
        """
        tool_specification_paths = list()
        connections = list()
        if not load_path:
            # noinspection PyCallByClass, PyTypeChecker, PyArgumentList
            answer = QFileDialog.getOpenFileName(
                self, 'Open project', project_dir(self._qsettings), 'Projects (*.proj)'
            )
            load_path = answer[0]
            if load_path == '':  # Cancel button clicked
                return False
        if not os.path.isfile(load_path):
            self.msg_error.emit("File <b>{0}</b> not found".format(load_path))
            return False
        if not load_path.lower().endswith('.proj'):
            self.msg_error.emit("Selected file has unsupported extension. Only .proj files are supported")
            return False
        # Load project from JSON file
        try:
            with open(load_path, 'r') as fh:
                try:
                    dicts = json.load(fh)
                except json.decoder.JSONDecodeError:
                    self.msg_error.emit("Error in file <b>{0}</b>. Not valid JSON. {0}".format(load_path))
                    return False
        except OSError:
            self.msg_error.emit("[OSError] Loading project file <b>{0}</b> failed".format(load_path))
            return False
        # Initialize UI
        self.clear_ui()
        # Parse project info
        project_dict = dicts['project']
        proj_name = project_dict['name']
        proj_desc = project_dict['description']
        try:
            work_dir = project_dict['work_dir']
        except KeyError:
            work_dir = ""
        try:
            tool_specification_paths = project_dict["tool_specifications"]
        except KeyError:
            try:
                tool_specification_paths = project_dict["tool_templates"]
            except KeyError:
                self.msg_warning.emit("Tool specifications not found in project file")
        try:
            connections = project_dict['connections']
        except KeyError:
            self.msg_warning.emit("No connections found in project file")
        # Create project
        self._project = SpineToolboxProject(self, proj_name, proj_desc, work_dir)
        # Init models and views
        self.setWindowTitle("Spine Toolbox    -- {} --".format(self._project.name))
        # Clear QTextBrowsers
        if clear_event_log:
            self.ui.textBrowser_eventlog.clear()
        self.ui.textBrowser_process_output.clear()
        # Populate project model with items read from JSON file
        self.init_models(tool_specification_paths)
        if not self._project.load(dicts['objects']):
            self.msg_error.emit("Loading project items failed")
            return False
        self.ui.treeView_project.expandAll()
        # Restore connections
        self.msg.emit("Restoring connections...")
        self.ui.graphicsView.restore_links(connections)
        # Simulate project execution after restoring links
        self._project.notify_changes_in_all_dags()
        self._project.connect_signals()
        # Initialize Design View scene
        self.ui.graphicsView.init_scene()
        self.update_recent_projects()
        self.msg.emit("Project <b>{0}</b> is now open".format(self._project.name))
        return True

    @Slot(name="show_recent_projects_menu")
    def show_recent_projects_menu(self):
        """Updates and sets up the recent projects menu to File-Open recent action."""
        if not self.recent_projects_menu.isVisible():
            self.recent_projects_menu = RecentProjectsPopupMenu(self)
            self.ui.actionOpen_recent.setMenu(self.recent_projects_menu)

    @Slot(name="save_project")
    def save_project(self):
        """Save project."""
        if not self._project:
            self.msg.emit("Please open or create a project first")
            return
        # Put project's tool specification definition files into a list
        tool_specifications = list()
        for i in range(self.tool_specification_model.rowCount()):
            tool_specifications.append(self.tool_specification_model.tool_specification(i).get_def_path())
        self._project.save(tool_specifications)
        self.msg.emit("Project saved to <b>{0}</b>".format(self._project.path))

    @Slot(name="save_project_as")
    def save_project_as(self):
        """Ask user for a new project name and save. Creates a duplicate of the open project."""
        if not self._project:
            self.msg.emit("Please open or create a project first")
            return
        msg = "This creates a copy of the current project. <br/><br/>New name:"
        # noinspection PyCallByClass
        answer = QInputDialog.getText(
            self, "New project name", msg, text=self._project.name, flags=Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )
        if not answer[1]:  # answer[str, bool]
            return
        name = answer[0]
        # Check if name is valid and copy project tree under a new name
        if not self._project.rename_project(name):
            return
        # Save project into new file
        self.save_project()
        # Load project
        self.open_project(self._project.path)
        return

    def init_models(self, tool_specification_paths):
        """Initialize application internal data models.

        Args:
            tool_specification_paths (list): List of tool definition file paths used in this project
        """
        self.init_project_item_model()
        self.ui.treeView_project.selectionModel().selectionChanged.connect(self.item_selection_changed)
        self.init_tool_specification_model(tool_specification_paths)

    def init_project_item_model(self):
        """Initializes project item model. Create root and category items and
        add them to the model."""
        root_item = RootProjectTreeItem()
        self.project_item_model = ProjectItemModel(self, root=root_item)
        for category, category_dict in self.categories.items():
            item_maker = category_dict["item_maker"]
            icon_maker = category_dict["icon_maker"]
            add_form_maker = category_dict["add_form_maker"]
            properties_ui = category_dict["properties_ui"]
            category_item = CategoryProjectTreeItem(category, "", item_maker, icon_maker, add_form_maker, properties_ui)
            self.project_item_model.insert_item(category_item)
        self.ui.treeView_project.setModel(self.project_item_model)
        self.ui.treeView_project.header().hide()
        self.ui.graphicsView.set_project_item_model(self.project_item_model)

    def init_tool_specification_model(self, tool_specification_paths):
        """Initializes Tool specification model.

        Args:
            tool_specification_paths (list): List of tool definition file paths used in this project
        """
        self.tool_specification_model_changed.emit(QStandardItemModel())
        self.tool_specification_model = ToolSpecificationModel()
        n_tools = 0
        self.msg.emit("Loading Tool specifications...")
        for path in tool_specification_paths:
            if path == '' or not path:
                continue
            # Add tool specification into project
            tool_cand = self._project.load_tool_specification_from_file(path)
            n_tools += 1
            if not tool_cand:
                continue
            # Add tool definition file path to tool instance variable
            tool_cand.set_def_path(path)
            # Insert tool into model
            self.tool_specification_model.insertRow(tool_cand)
            # self.msg.emit("Tool specification <b>{0}</b> ready".format(tool_cand.name))
        # Set model to the tool specification list view
        self.ui.listView_tool_specifications.setModel(self.tool_specification_model)
        # Set model to Tool project item combo box
        self.tool_specification_model_changed.emit(self.tool_specification_model)
        # Note: If ToolSpecificationModel signals are in use, they should be reconnected here.
        # Reconnect ToolSpecificationModel and QListView signals. Make sure that signals are connected only once.
        n_recv_sig1 = self.ui.listView_tool_specifications.receivers(
            SIGNAL("doubleClicked(QModelIndex)")
        )  # nr of receivers
        if n_recv_sig1 == 0:
            # logging.debug("Connecting doubleClicked signal for QListView")
            self.ui.listView_tool_specifications.doubleClicked.connect(self.edit_tool_specification)
        elif n_recv_sig1 > 1:  # Check that this never gets over 1
            logging.error("Number of receivers for QListView doubleClicked signal is now: %d", n_recv_sig1)
        else:
            pass  # signal already connected
        n_recv_sig2 = self.ui.listView_tool_specifications.receivers(SIGNAL("customContextMenuRequested(QPoint)"))
        if n_recv_sig2 == 0:
            # logging.debug("Connecting customContextMenuRequested signal for QListView")
            self.ui.listView_tool_specifications.customContextMenuRequested.connect(
                self.show_tool_specification_context_menu
            )
        elif n_recv_sig2 > 1:  # Check that this never gets over 1
            logging.error("Number of receivers for QListView customContextMenuRequested signal is now: %d", n_recv_sig2)
        else:
            pass  # signal already connected
        if n_tools == 0:
            self.msg_warning.emit("Project has no Tool specifications")

    def restore_ui(self):
        """Restore UI state from previous session."""
        window_size = self._qsettings.value("mainWindow/windowSize", defaultValue="false")
        window_pos = self._qsettings.value("mainWindow/windowPosition", defaultValue="false")
        window_state = self._qsettings.value("mainWindow/windowState", defaultValue="false")
        splitter_state = self._qsettings.value("mainWindow/projectDockWidgetSplitterState", defaultValue="false")
        window_maximized = self._qsettings.value("mainWindow/windowMaximized", defaultValue='false')  # returns str
        n_screens = self._qsettings.value("mainWindow/n_screens", defaultValue=1)  # number of screens on last exit
        # noinspection PyArgumentList
        n_screens_now = len(QGuiApplication.screens())  # Number of screens now
        # Note: cannot use booleans since Windows saves them as strings to registry
        if not window_size == "false":
            self.resize(window_size)  # Expects QSize
        if not window_pos == "false":
            self.move(window_pos)  # Expects QPoint
        if not window_state == "false":
            self.restoreState(window_state, version=1)  # Toolbar and dockWidget positions. Expects QByteArray
        if not splitter_state == "false":
            self.ui.splitter.restoreState(splitter_state)  # Project Dock Widget splitter position. Expects QByteArray
        if window_maximized == 'true':
            self.setWindowState(Qt.WindowMaximized)
        if n_screens_now < int(n_screens):
            # There are less screens available now than on previous application startup
            # Move main window to position 0,0 to make sure that it is not lost on another screen that does not exist
            self.move(0, 0)

    def clear_ui(self):
        """Clean UI to make room for a new or opened project."""
        if not self.project():
            return
        item_names = self.project_item_model.item_names()
        for name in item_names:
            ind = self.project_item_model.find_item(name)
            self.remove_item(ind)
        self.activate_no_selection_tab()  # Clear properties widget
        if self._project:
            self._project.deleteLater()
        self._project = None
        self.tool_specification_model = None
        self.ui.textBrowser_eventlog.clear()
        self.ui.textBrowser_process_output.clear()
        self.ui.graphicsView.scene().clear()  # Clear all items from scene

    @Slot("QItemSelection", "QItemSelection", name="item_selection_changed")
    def item_selection_changed(self, selected, deselected):
        """Synchronize selection with scene. Check if only one item is selected and make it the
        active item: disconnect signals of previous active item, connect signals of current active item
        and show correct properties tab for the latter.
        """
        inds = self.ui.treeView_project.selectedIndexes()
        proj_items = [self.project_item_model.item(i).project_item for i in inds]
        # NOTE: Category items are not selectable anymore
        # Sync selection with the scene
        if proj_items:
            scene = self.ui.graphicsView.scene()
            scene.sync_selection = False  # This tells the scene not to sync back
            scene.clearSelection()
            for item in proj_items:
                item.get_icon().setSelected(True)
            scene.sync_selection = True
        # Refresh active item if needed
        if len(proj_items) == 1:
            new_active_project_item = proj_items[0]
        else:
            new_active_project_item = None
        if self.active_project_item and self.active_project_item != new_active_project_item:
            # Deactivate old active project item
            ret = self.active_project_item.deactivate()
            if not ret:
                self.msg_error.emit(
                    "Something went wrong in disconnecting {0} signals".format(self.active_project_item.name)
                )
        self.active_project_item = new_active_project_item
        if self.active_project_item:
            # Activate new active project item
            self.active_project_item.activate()
            self.activate_item_tab(self.active_project_item)
        else:
            self.activate_no_selection_tab()

    def activate_no_selection_tab(self):
        """Shows 'No Selection' tab."""
        for i in range(self.ui.tabWidget_item_properties.count()):
            if self.ui.tabWidget_item_properties.tabText(i) == "No Selection":
                self.ui.tabWidget_item_properties.setCurrentIndex(i)
                break
        self.ui.dockWidget_item.setWindowTitle("Properties")

    def activate_item_tab(self, item):
        """Shows project item properties tab according to item type.
        Note: Does not work if a category item is given as argument.

        Args:
            item (ProjectItem): Instance of a project item
        """
        # Find tab index according to item type
        for i in range(self.ui.tabWidget_item_properties.count()):
            if self.ui.tabWidget_item_properties.tabText(i) == item.item_type():
                self.ui.tabWidget_item_properties.setCurrentIndex(i)
                break
        # Set QDockWidget title to selected item's type
        self.ui.dockWidget_item.setWindowTitle(item.item_type() + " Properties")

    @Slot(name="open_tool_specification")
    def open_tool_specification(self):
        """Open a file dialog so the user can select an existing tool specification .json file.
        Continue loading the tool specification into the Project if successful.
        """
        if not self._project:
            self.msg.emit("Please create a new project or open an existing one first")
            return
        # noinspection PyCallByClass, PyTypeChecker, PyArgumentList
        answer = QFileDialog.getOpenFileName(
            self,
            "Select Tool specification file",
            os.path.join(project_dir(self._qsettings), os.path.pardir),
            "JSON (*.json)",
        )
        if answer[0] == "":  # Cancel button clicked
            return
        def_file = os.path.abspath(answer[0])
        # Load tool definition
        tool_specification = self._project.load_tool_specification_from_file(def_file)
        if not tool_specification:
            return
        if self.tool_specification_model.find_tool_specification(tool_specification.name):
            # Tool specification already added to project
            self.msg_warning.emit("Tool specification <b>{0}</b> already in project".format(tool_specification.name))
            return
        # Add definition file path into tool specification
        tool_specification.set_def_path(def_file)
        self.add_tool_specification(tool_specification)

    def add_tool_specification(self, tool_specification):
        """Add a ToolSpecification instance to project, which then can be added to a Tool item.
        Add tool specification file path into project file (.proj)

        tool_specification (ToolSpecification): Tool specification that is added to project
        """
        def_file = tool_specification.get_def_path()  # Definition file path (.json)
        # Insert tool specification into model
        self.tool_specification_model.insertRow(tool_specification)
        # Save Tool def file path to project file
        project_file = self._project.path  # Path to project file
        if project_file.lower().endswith('.proj'):
            # Manipulate project file contents
            try:
                with open(project_file, 'r') as fh:
                    dicts = json.load(fh)
            except OSError:
                self.msg_error.emit("OSError: Could not load file <b>{0}</b>".format(project_file))
                return
            # Get project settings
            project_dict = dicts['project']
            objects_dict = dicts['objects']
            try:
                tools = project_dict['tool_specifications']
                if def_file not in tools:
                    tools.append(def_file)
                project_dict['tool_specifications'] = tools
            except KeyError:
                project_dict['tool_specifications'] = [def_file]
            # Save dictionaries back to project save file
            dicts['project'] = project_dict
            dicts['objects'] = objects_dict
            with open(project_file, 'w') as fp:
                json.dump(dicts, fp, indent=4)
            self.msg_success.emit("Tool specification <b>{0}</b> added to project".format(tool_specification.name))
        else:
            self.msg_error.emit("Unsupported project filename {0}. Extension should be .proj.".format(project_file))
            return

    def update_tool_specification(self, row, tool_specification):
        """Update a Tool specification and refresh Tools that use it.

        Args:
            row (int): Row of tool specification in ToolSpecificationModel
            tool_specification (ToolSpecification): An updated Tool specification
        """
        if not self.tool_specification_model.update_tool_specification(tool_specification, row):
            self.msg_error.emit("Unable to update Tool specification <b>{0}</b>".format(tool_specification.name))
            return
        self.msg_success.emit("Tool specification <b>{0}</b> successfully updated".format(tool_specification.name))
        # Reattach Tool specification to any Tools that use it
        # Find the updated tool specification from ToolSpecificationModel
        specification = self.tool_specification_model.find_tool_specification(tool_specification.name)
        if not specification:
            self.msg_error.emit("Could not find Tool specification <b>{0}</b>".format(tool_specification.name))
            return
        # Get all Tool project items
        tools = [item.project_item for item in self.project_item_model.items("Tools")]
        for tool_item in tools:
            if not tool_item.tool_specification():
                continue
            if tool_item.tool_specification().name == tool_specification.name:
                tool_item.update_execution_mode(specification.execute_in_work)
                tool_item.set_tool_specification(specification)
                self.msg.emit(
                    "Tool specification <b>{0}</b> reattached to Tool <b>{1}</b>".format(
                        specification.name, tool_item.name
                    )
                )

    @Slot(name="remove_selected_tool_specification")
    def remove_selected_tool_specification(self):
        """Prepare to remove tool specification selected in QListView."""
        if not self._project:
            self.msg.emit("Please create a new project or open an existing one first")
            return
        try:
            index = self.ui.listView_tool_specifications.selectedIndexes()[0]
        except IndexError:
            # Nothing selected
            self.msg.emit("Select a Tool specification to remove")
            return
        if not index.isValid():
            return
        self.remove_tool_specification(index)

    @Slot("QModelIndex", name="remove_tool_specification")
    def remove_tool_specification(self, index):
        """Remove tool specification from ToolSpecificationModel
        and tool specification file path from project file.
        Removes also Tool specifications from all Tool items
        that use this specification."""
        sel_tool = self.tool_specification_model.tool_specification(index.row())
        tool_def_path = sel_tool.def_file_path
        message = "Remove Tool Specification <b>{0}</b> from Project?".format(sel_tool.name)
        message_box = QMessageBox(
            QMessageBox.Question,
            "Remove Tool Specification",
            message,
            buttons=QMessageBox.Ok | QMessageBox.Cancel,
            parent=self,
        )
        message_box.button(QMessageBox.Ok).setText("Remove Specification")
        answer = message_box.exec_()
        if answer != QMessageBox.Ok:
            return
        # Remove tool def file path from the project file
        project_file = self._project.path
        if not project_file.lower().endswith('.proj'):
            self.msg_error.emit("Project file extension not supported. Needs to be .proj.")
            return
        # Read project data from JSON file
        try:
            with open(project_file, 'r') as fh:
                dicts = json.load(fh)
        except OSError:
            self.msg_error.emit("OSError: Could not load file <b>{0}</b>".format(project_file))
            return
        # Get project settings
        project_dict = dicts['project']
        object_dict = dicts['objects']
        if not self.tool_specification_model.removeRow(index.row()):
            self.msg_error.emit("Error in removing Tool specification <b>{0}</b>".format(sel_tool.name))
            return
        try:
            tools = project_dict['tool_specifications']
            tools.remove(tool_def_path)
            # logging.debug("tools list after removal:{}".format(tools))
            project_dict['tool_specifications'] = tools
        except KeyError:
            self.msg_error.emit(
                "This is odd. tool_specifications list not found in project file <b>{0}</b>".format(project_file)
            )
            return
        except ValueError:
            self.msg_error.emit(
                "This is odd. Tool specification file path <b>{0}</b> not found "
                "in project file <b>{1}</b>".format(tool_def_path, project_file)
            )
            return
        # Save dictionaries back to JSON file
        dicts['project'] = project_dict
        dicts['objects'] = object_dict
        with open(project_file, 'w') as fp:
            json.dump(dicts, fp, indent=4)
        self.msg_success.emit("Tool specification removed")

    def remove_all_items(self):
        """Slot for Remove All button."""
        if not self._project:
            self.msg.emit("No project items to remove")
            return
        msg = "Remove all items from project?"
        message_box = QMessageBox(
            QMessageBox.Question, "Remove All Items", msg, buttons=QMessageBox.Ok | QMessageBox.Cancel, parent=self
        )
        message_box.button(QMessageBox.Ok).setText("Remove Items")
        answer = message_box.exec_()
        if answer != QMessageBox.Ok:
            return
        item_names = self.project_item_model.item_names()
        n = len(item_names)
        if n == 0:
            return
        for name in item_names:
            ind = self.project_item_model.find_item(name)
            delete_int = int(self._qsettings.value("appSettings/deleteData", defaultValue="0"))
            delete_bool = delete_int != 0
            self.remove_item(ind, delete_item=delete_bool)
        self.msg.emit("All {0} items removed from project".format(n))
        self.activate_no_selection_tab()
        self.ui.graphicsView.scene().clear()
        self.ui.graphicsView.init_scene()

    def remove_item(self, ind, delete_item=False, check_dialog=False):
        """Removes item from project when it's index in the project model is known.
        To remove all items in project, loop all indices through this method.
        This method is used in both opening and creating a new project as
        well as when item(s) are deleted from project.
        Use delete_item=False when closing the project or creating a new one.
        Setting delete_item=True deletes the item irrevocably. This means that
        data directories will be deleted from the hard drive. Handles also
        removing the node from the dag graph that contains it.

        Args:
            ind (QModelIndex): Index of removed item in project model
            delete_item (bool): If set to True, deletes the directories and data associated with the item
            check_dialog (bool): If True, shows 'Are you sure?' message box
        """
        item = self.project_item_model.item(ind)
        name = item.name
        if check_dialog:
            if not delete_item:
                msg = (
                    "Remove item <b>{}</b> from project?".format(name)
                    + " Item data directory will still be available in the project directory after this operation."
                )
            else:
                msg = "Remove item <b>{}</b> and its data directory from project?".format(name)
            msg = msg + "<br><br>Tip: Remove items by pressing 'Delete' key to bypass this dialog."
            # noinspection PyCallByClass, PyTypeChecker
            message_box = QMessageBox(
                QMessageBox.Question, "Remove Item", msg, buttons=QMessageBox.Ok | QMessageBox.Cancel, parent=self
            )
            message_box.button(QMessageBox.Ok).setText("Remove Item")
            answer = message_box.exec_()
            if answer != QMessageBox.Ok:
                return
        try:
            data_dir = item.project_item.data_dir
        except AttributeError:
            data_dir = None
        # Remove item from project model
        if not self.project_item_model.remove_item(item, parent=ind.parent()):
            self.msg_error.emit("Removing item <b>{0}</b> from project failed".format(name))
        # Remove item icon and connected links (QGraphicsItems) from scene
        icon = item.project_item.get_icon()
        self.ui.graphicsView.remove_icon(icon)
        self._project.dag_handler.remove_node_from_graph(name)
        item.project_item.tear_down()
        if delete_item:
            if data_dir:
                # Remove data directory and all its contents
                self.msg.emit("Removing directory <b>{0}</b>".format(data_dir))
                try:
                    if not erase_dir(data_dir):
                        self.msg_error.emit("Directory does not exist")
                except OSError:
                    self.msg_error.emit("[OSError] Removing directory failed. Check directory permissions.")
        self.msg.emit("Item <b>{0}</b> removed from project".format(name))

    @Slot("QUrl", name="open_anchor")
    def open_anchor(self, qurl):
        """Open file explorer in the directory given in qurl.

        Args:
            qurl (QUrl): Directory path or a file to open
        """
        if qurl.url() == "#":  # This is a Tip so do not try to open the URL
            return
        path = qurl.toLocalFile()  # Path to result folder
        # noinspection PyTypeChecker, PyCallByClass, PyArgumentList
        res = QDesktopServices.openUrl(qurl)
        if not res:
            self.msg_error.emit("Opening path {} failed".format(path))

    @Slot("QModelIndex", name="edit_tool_specification")
    def edit_tool_specification(self, index):
        """Open the tool specification widget for editing an existing tool specification.

        Args:
            index (QModelIndex): Index of the item (from double-click or contex menu signal)
        """
        if not index.isValid():
            return
        tool_specification = self.tool_specification_model.tool_specification(index.row())
        # Open spec in Tool specification edit widget
        self.show_tool_specification_form(tool_specification)

    @busy_effect
    @Slot("QModelIndex", name="open_tool_specification_file")
    def open_tool_specification_file(self, index):
        """Open the Tool specification definition file in the default (.json) text-editor.

        Args:
            index (QModelIndex): Index of the item
        """
        if not index.isValid():
            return
        tool_specification = self.tool_specification_model.tool_specification(index.row())
        file_path = tool_specification.get_def_path()
        # Check if file exists first. openUrl may return True if file doesn't exist
        # TODO: this could still fail if the file is deleted or renamed right after the check
        if not os.path.isfile(file_path):
            logging.error("Failed to open editor for %s", file_path)
            self.msg_error.emit("Tool specification file <b>{0}</b> not found.".format(file_path))
            return
        tool_specification_url = "file:///" + file_path
        # Open Tool specification file in editor
        # noinspection PyTypeChecker, PyCallByClass, PyArgumentList
        res = QDesktopServices.openUrl(QUrl(tool_specification_url, QUrl.TolerantMode))
        if not res:
            logging.error("Failed to open editor for %s", tool_specification_url)
            self.msg_error.emit(
                "Unable to open Tool specification file {0}. Make sure that <b>.json</b> "
                "files are associated with a text editor. For example on Windows "
                "10, go to Control Panel -> Default Programs to do this.".format(file_path)
            )
        return

    @busy_effect
    @Slot("QModelIndex", name="open_tool_main_program_file")
    def open_tool_main_program_file(self, index):
        """Open the tool specification's main program file in the default editor.

        Args:
            index (QModelIndex): Index of the item
        """
        if not index.isValid():
            return
        tool_item = self.tool_specification_model.tool_specification(index.row())
        file_path = os.path.join(tool_item.path, tool_item.includes[0])
        # Check if file exists first. openUrl may return True even if file doesn't exist
        # TODO: this could still fail if the file is deleted or renamed right after the check
        if not os.path.isfile(file_path):
            self.msg_error.emit("Tool main program file <b>{0}</b> not found.".format(file_path))
            return
        ext = os.path.splitext(os.path.split(file_path)[1])[1]
        if ext in [".bat", ".exe"]:
            self.msg_warning.emit(
                "Sorry, opening files with extension <b>{0}</b> not supported. "
                "Please open the file manually.".format(ext)
            )
            return
        main_program_url = "file:///" + file_path
        # Open Tool specification main program file in editor
        # noinspection PyTypeChecker, PyCallByClass, PyArgumentList
        res = QDesktopServices.openUrl(QUrl(main_program_url, QUrl.TolerantMode))
        if not res:
            filename, file_extension = os.path.splitext(file_path)
            self.msg_error.emit(
                "Unable to open Tool specification main program file {0}. "
                "Make sure that <b>{1}</b> "
                "files are associated with an editor. E.g. on Windows "
                "10, go to Control Panel -> Default Programs to do this.".format(filename, file_extension)
            )
        return

    @Slot(name="export_as_graphml")
    def export_as_graphml(self):
        """Exports all DAGs in project to separate GraphML files."""
        if not self.project():
            self.msg.emit("Please open or create a project first")
            return
        self.project().export_graphs()

    @Slot(name="_handle_zoom_minus_pressed")
    def _handle_zoom_minus_pressed(self):
        """Slot for handling case when '-' button in menu is pressed."""
        self.ui.graphicsView.zoom_out()

    @Slot(name="_handle_zoom_plus_pressed")
    def _handle_zoom_plus_pressed(self):
        """Slot for handling case when '+' button in menu is pressed."""
        self.ui.graphicsView.zoom_in()

    @Slot(name="_handle_zoom_reset_pressed")
    def _handle_zoom_reset_pressed(self):
        """Slot for handling case when 'reset zoom' button in menu is pressed."""
        self.ui.graphicsView.reset_zoom()

    def setup_zoom_widget_action(self):
        """Setups zoom widget action in view menu."""
        self.zoom_widget_action = ZoomWidgetAction(self.ui.menuView)
        self.ui.menuView.addSeparator()
        self.ui.menuView.addAction(self.zoom_widget_action)

    @Slot(name="restore_dock_widgets")
    def restore_dock_widgets(self):
        """Dock all floating and or hidden QDockWidgets back to the main window."""
        for dock in self.findChildren(QDockWidget):
            if not dock.isVisible():
                dock.setVisible(True)
            if dock.isFloating():
                dock.setFloating(False)

    def set_debug_qactions(self):
        """Set shortcuts for QActions that may be needed in debugging."""
        self.show_properties_tabbar.setShortcut(QKeySequence(Qt.CTRL + Qt.Key_0))
        self.show_supported_img_formats.setShortcut(QKeySequence(Qt.CTRL + Qt.Key_8))
        self.test_variable_push.setShortcut(QKeySequence(Qt.CTRL + Qt.Key_7))
        self.addAction(self.show_properties_tabbar)
        self.addAction(self.show_supported_img_formats)
        self.addAction(self.test_variable_push)

    def add_toggle_view_actions(self):
        """Add toggle view actions to View menu."""
        self.ui.menuToolbars.addAction(self.item_toolbar.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_project.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_eventlog.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_process_output.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_item.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_python_repl.toggleViewAction())
        self.ui.menuDock_Widgets.addAction(self.ui.dockWidget_julia_repl.toggleViewAction())

    def toggle_properties_tabbar_visibility(self):
        """Shows or hides the tab bar in properties dock widget. For debugging purposes."""
        if self.ui.tabWidget_item_properties.tabBar().isVisible():
            self.ui.tabWidget_item_properties.tabBar().hide()
        else:
            self.ui.tabWidget_item_properties.tabBar().show()

    def update_datetime(self):
        """Returns a boolean, which determines whether
        date and time is prepended to every Event Log message."""
        d = int(self._qsettings.value("appSettings/dateTime", defaultValue="2"))
        return d != 0

    @Slot(str, name="add_message")
    def add_message(self, msg):
        """Append regular message to Event Log.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:white;white-space: pre-wrap;'>"
        date_str = get_datetime(show=self.show_datetime)
        message = open_tag + date_str + msg + "</span>"
        self.ui.textBrowser_eventlog.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    @Slot(str, name="add_success_message")
    def add_success_message(self, msg):
        """Append message with green text color to Event Log.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:#00ff00;white-space: pre-wrap;'>"
        date_str = get_datetime(show=self.show_datetime)
        message = open_tag + date_str + msg + "</span>"
        self.ui.textBrowser_eventlog.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    @Slot(str, name="add_error_message")
    def add_error_message(self, msg):
        """Append message with red color to Event Log.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:#ff3333;white-space: pre-wrap;'>"
        date_str = get_datetime(show=self.show_datetime)
        message = open_tag + date_str + msg + "</span>"
        self.ui.textBrowser_eventlog.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    @Slot(str, name="add_warning_message")
    def add_warning_message(self, msg):
        """Append message with yellow (golden) color to Event Log.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:yellow;white-space: pre-wrap;'>"
        date_str = get_datetime(show=self.show_datetime)
        message = open_tag + date_str + msg + "</span>"
        self.ui.textBrowser_eventlog.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    @Slot(str, name="add_process_message")
    def add_process_message(self, msg):
        """Writes message from stdout to process output QTextBrowser.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:white;white-space: pre;'>"
        message = open_tag + msg + "</span>"
        self.ui.textBrowser_process_output.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    @Slot(str, name="add_process_error_message")
    def add_process_error_message(self, msg):
        """Writes message from stderr to process output QTextBrowser.

        Args:
            msg (str): String written to QTextBrowser
        """
        open_tag = "<span style='color:#ff3333;white-space: pre;'>"
        message = open_tag + msg + "</span>"
        self.ui.textBrowser_process_output.append(message)
        # noinspection PyArgumentList
        QApplication.processEvents()

    def show_add_project_item_form(self, item_category, x=0, y=0):
        """Show add project item widget."""
        if not self._project:
            self.msg.emit("Please open or create a project first")
            return
        category_ind = self.project_item_model.find_category(item_category)
        if not category_ind:
            self.msg_error.emit("Category {0} not found".format(item_category))
            return
        category = self.project_item_model.item(category_ind)
        self.add_project_item_form = category._add_form_maker(self, x, y)
        self.add_project_item_form.show()

    @Slot(name="show_tool_specification_form")
    def show_tool_specification_form(self, tool_specification=None):
        """Show tool specification widget."""
        if not self._project:
            self.msg.emit("Please open or create a project first")
            return
        form = ToolSpecificationWidget(self, tool_specification)
        form.show()

    @Slot(name="show_settings")
    def show_settings(self):
        """Show Settings widget."""
        self.settings_form = SettingsWidget(self)
        self.settings_form.show()

    @Slot(name="show_tool_config_asst")
    def show_tool_config_asst(self):
        """Show Tool configuration assistant widget."""
        form = ToolConfigurationAssistantWidget(self)
        form.show()

    @Slot(name="show_about")
    def show_about(self):
        """Show About Spine Toolbox form."""
        form = AboutWidget(self)
        form.show()

    @Slot(name="show_user_guide")
    def show_user_guide(self):
        """Open Spine Toolbox documentation index page in browser."""
        doc_index_path = os.path.join(DOCUMENTATION_PATH, "index.html")
        index_url = "file:///" + doc_index_path
        # noinspection PyTypeChecker, PyCallByClass, PyArgumentList
        res = QDesktopServices.openUrl(QUrl(index_url, QUrl.TolerantMode))
        if not res:
            logging.error("Failed to open editor for %s", index_url)
            self.msg_error.emit("Unable to open file <b>{0}</b>".format(doc_index_path))

    @Slot(name="show_getting_started_guide")
    def show_getting_started_guide(self):
        """Open Spine Toolbox Getting Started HTML page in browser."""
        getting_started_path = os.path.join(DOCUMENTATION_PATH, "getting_started.html")
        index_url = "file:///" + getting_started_path
        # noinspection PyTypeChecker, PyCallByClass, PyArgumentList
        res = QDesktopServices.openUrl(QUrl(index_url, QUrl.TolerantMode))
        if not res:
            logging.error("Failed to open editor for %s", index_url)
            self.msg_error.emit("Unable to open file <b>{0}</b>".format(getting_started_path))

    @Slot("QPoint", name="show_item_context_menu")
    def show_item_context_menu(self, pos):
        """Context menu for project items listed in the project QTreeView.

        Args:
            pos (QPoint): Mouse position
        """
        ind = self.ui.treeView_project.indexAt(pos)
        global_pos = self.ui.treeView_project.viewport().mapToGlobal(pos)
        self.show_project_item_context_menu(global_pos, ind)

    @Slot("QPoint", str, name="show_item_image_context_menu")
    def show_item_image_context_menu(self, pos, name):
        """Context menu for project item images on the QGraphicsView.

        Args:
            pos (QPoint): Mouse position
            name (str): The name of the concerned item
        """
        ind = self.project_item_model.find_item(name)
        self.show_project_item_context_menu(pos, ind)

    def show_project_item_context_menu(self, pos, ind):
        """Create and show project item context menu.

        Args:
            pos (QPoint): Mouse position
            ind (QModelIndex): Index of concerned item
        """
        if not self.project():
            return
        if not ind.isValid():
            # Clicked on a blank area, show the project item model context menu
            self.project_item_context_menu = ProjectItemModelContextMenu(self, pos)
            action = self.project_item_context_menu.get_action()
            if action == "Open project directory...":
                file_url = "file:///" + self._project.project_dir
                self.open_anchor(QUrl(file_url, QUrl.TolerantMode))
            elif action == "Export project to GraphML":
                self.project().export_graphs()
            else:  # No option selected
                pass
        else:
            # Clicked on an item, show the custom context menu for that item
            item = self.project_item_model.item(ind)
            self.project_item_context_menu = item.custom_context_menu(self, pos)
            action = self.project_item_context_menu.get_action()
            item.apply_context_menu_action(self, action)
        self.project_item_context_menu.deleteLater()
        self.project_item_context_menu = None

    def show_link_context_menu(self, pos, link):
        """Context menu for connection links.

        Args:
            pos (QPoint): Mouse position
            link (Link(QGraphicsPathItem)): The concerned link
        """
        self.link_context_menu = LinkContextMenu(self, pos, link)
        option = self.link_context_menu.get_action()
        if option == "Remove connection":
            self.ui.graphicsView.remove_link(link)
            return
        if option == "Take connection":
            self.ui.graphicsView.take_link(link)
            return
        if option == "Send to bottom":
            link.send_to_bottom()
        self.link_context_menu.deleteLater()
        self.link_context_menu = None

    @Slot("QPoint", name="show_tool_specification_context_menu")
    def show_tool_specification_context_menu(self, pos):
        """Context menu for tool specifications.

        Args:
            pos (QPoint): Mouse position
        """
        if not self.project():
            return
        ind = self.ui.listView_tool_specifications.indexAt(pos)
        global_pos = self.ui.listView_tool_specifications.viewport().mapToGlobal(pos)
        self.tool_specification_context_menu = ToolSpecificationContextMenu(self, global_pos, ind)
        option = self.tool_specification_context_menu.get_action()
        if option == "Edit Tool specification":
            self.edit_tool_specification(ind)
        elif option == "Edit main program file...":
            self.open_tool_main_program_file(ind)
        elif option == "Open main program directory...":
            tool_specification_path = self.tool_specification_model.tool_specification(ind.row()).path
            path_url = "file:///" + tool_specification_path
            self.open_anchor(QUrl(path_url, QUrl.TolerantMode))
        elif option == "Open Tool specification file...":
            self.open_tool_specification_file(ind)
        elif option == "Remove Tool specification":
            self.remove_tool_specification(ind)
        else:  # No option selected
            pass
        self.tool_specification_context_menu.deleteLater()
        self.tool_specification_context_menu = None

    def tear_down_items(self):
        """Calls the tear_down method on all project items, so they can clean up their mess if needed."""
        if not self._project:
            return
        for item in self.project_item_model.items():
            if isinstance(item, LeafProjectTreeItem):
                item.project_item.tear_down()

    def _tasks_before_exit(self):
        """
        Returns a list of tasks to perform before exiting the application.

        Possible tasks are:

        - `"prompt exit"`: prompt user if quitting is really desired
        - `"prompt save"`: prompt user if project should be saved before quitting
        - `"save"`: save project before quitting

        Returns:
            a list containing zero or more tasks
        """
        show_confirm_exit = int(self._qsettings.value("appSettings/showExitPrompt", defaultValue="2"))
        save_at_exit = (
            int(self._qsettings.value("appSettings/saveAtExit", defaultValue="1")) if self._project is not None else 0
        )
        if show_confirm_exit != 2:
            # Don't prompt for exit
            if save_at_exit == 0:
                return []
            if save_at_exit == 1:
                # We still need to prompt for saving
                return ["prompt save"]
            return ["save"]
        if save_at_exit == 0:
            return ["prompt exit"]
        if save_at_exit == 1:
            return ["prompt save"]
        return ["prompt exit", "save"]

    def _perform_pre_exit_tasks(self):
        """
        Prompts user to confirm quitting and saves the project if necessary.

        Returns:
            True if exit should proceed, False if the process was cancelled
        """
        tasks = self._tasks_before_exit()
        for task in tasks:
            if task == "prompt exit":
                if not self._confirm_exit():
                    return False
            elif task == "prompt save":
                if not self._confirm_save_and_exit():
                    return False
            elif task == "save":
                self.save_project()
        return True

    def _confirm_exit(self):
        """
        Confirms exiting from user.

        Returns:
            True if exit should proceed, False if user cancelled
        """
        msg = QMessageBox(parent=self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Confirm exit")
        msg.setText("Are you sure you want to exit Spine Toolbox?")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.button(QMessageBox.Ok).setText("Exit")
        chkbox = QCheckBox()
        chkbox.setText("Do not ask me again")
        msg.setCheckBox(chkbox)
        answer = msg.exec_()  # Show message box
        if answer == QMessageBox.Ok:
            # Update conf file according to checkbox status
            if not chkbox.checkState():
                show_prompt = "2"  # 2 as in True
            else:
                show_prompt = "0"  # 0 as in False
            self._qsettings.setValue("appSettings/showExitPrompt", show_prompt)
            return True
        return False

    def _confirm_save_and_exit(self):
        """
        Confirms exit from user and saves the project if requested.

        Returns:
            True if exiting should proceed, False if user cancelled
        """
        msg = QMessageBox(parent=self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Save project before exiting")
        msg.setText("Exiting Spine Toolbox. Save changes to project?")
        msg.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        msg.button(QMessageBox.Save).setText("Save And Exit")
        msg.button(QMessageBox.Discard).setText("Exit without Saving")
        chkbox = QCheckBox()
        chkbox.setText("Do not ask me again")
        msg.setCheckBox(chkbox)
        answer = msg.exec_()
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            self.save_project()
        chk = chkbox.checkState()
        if chk == 2:
            if answer == QMessageBox.Save:
                self._qsettings.setValue("appSettings/saveAtExit", "2")
            elif answer == QMessageBox.Discard:
                self._qsettings.setValue("appSettings/saveAtExit", "0")
        return True

    def remove_path_from_recent_projects(self, p):
        """Removes entry that contains given path from the recent project files list in QSettings.

        Args:
            p (str): Full path to a project file (.proj)
        """
        recents = self._qsettings.value("appSettings/recentProjects", defaultValue=None)
        if not recents:
            return
        recents = str(recents)
        recents_list = recents.split("\n")
        for entry in recents_list:
            _, path = entry.split("<>")
            if path == p:
                recents_list.pop(recents_list.index(entry))
                break
        updated_recents = "\n".join(recents_list)
        # Save updated recent paths
        self._qsettings.setValue("appSettings/recentProjects", updated_recents)
        self._qsettings.sync()  # Commit change immediately
        self.msg_error.emit("Opening selected project failed. Project file <b>{0}</b> may have been removed.".format(p))

    def update_recent_projects(self):
        """Adds a new entry to QSettings variable that remembers the five most recent project paths."""
        recents = self._qsettings.value("appSettings/recentProjects", defaultValue=None)
        entry = self.project().name + "<>" + self.project().path
        if not recents:
            updated_recents = entry
        else:
            recents = str(recents)
            recents_list = recents.split("\n")
            # Add path only if it's not in the list already
            if entry not in recents_list:
                recents_list.insert(0, entry)
                if len(recents_list) > 5:
                    recents_list.pop()
            else:
                # If path was on the list, move it as the first item
                recents_list.insert(0, recents_list.pop(recents_list.index(entry)))
            updated_recents = "\n".join(recents_list)
        # Save updated recent paths
        self._qsettings.setValue("appSettings/recentProjects", updated_recents)
        self._qsettings.sync()  # Commit change immediately

    def closeEvent(self, event):
        """Method for handling application exit.

        Args:
             event (QCloseEvent): PySide2 event
        """
        # Show confirm exit message box
        exit_confirmed = self._perform_pre_exit_tasks()
        if not exit_confirmed:
            event.ignore()
            return
        # Save settings
        if self._project is None:
            self._qsettings.setValue("appSettings/previousProject", "")
        else:
            self._qsettings.setValue("appSettings/previousProject", self._project.path)
            self.update_recent_projects()
            # Show save project prompt
        self._qsettings.setValue("mainWindow/windowSize", self.size())
        self._qsettings.setValue("mainWindow/windowPosition", self.pos())
        self._qsettings.setValue("mainWindow/windowState", self.saveState(version=1))
        self._qsettings.setValue("mainWindow/projectDockWidgetSplitterState", self.ui.splitter.saveState())
        if self.windowState() == Qt.WindowMaximized:
            self._qsettings.setValue("mainWindow/windowMaximized", True)
        else:
            self._qsettings.setValue("mainWindow/windowMaximized", False)
        # Save number of screens
        # noinspection PyArgumentList
        self._qsettings.setValue("mainWindow/n_screens", len(QGuiApplication.screens()))
        self.julia_repl.shutdown_jupyter_kernel()
        self.python_repl.shutdown_kernel()
        self.tear_down_items()
        event.accept()

    def _serialize_selected_items(self):
        """
        Serializes selected project items into a dictionary.

        The serialization protocol tries to imitate the format in which projects are saved.
        The format of the dictonary is following:
        `{"item_category_1": [{"name": "item_1_name", ...}, ...], ...}`

        Returns:
             a dict containing serialized version of selected project items
        """
        selected_project_items = self.ui.graphicsView.scene().selectedItems()
        serialized_items = dict()
        for item_icon in selected_project_items:
            if not isinstance(item_icon, ProjectItemIcon):
                continue
            name = item_icon.name()
            index = self.project_item_model.find_item(name)
            item = self.project_item_model.item(index)
            category = self.project_item_model.category_of_item(item.name)
            category_items = serialized_items.setdefault(category.name, list())
            item_dict = item.project_item.item_dict()
            item_dict["name"] = item.name
            category_items.append(item_dict)
        return serialized_items

    def _deserialized_item_position_shifts(self, serialized_items):
        """
        Calculates horizontal and vertical shifts for project items being deserialized.

        If the mouse cursor is on the Design view we try to place the items unders the cursor.
        Otherwise the items will get a small shift so they don't overlap a possible item below.
        In case the items don't fit the scene rect we clamp their coordinates within it.

        Args:
            serialized_items (dict): a dictionary of serialized items being deserialized
        Returns:
            a tuple of (horizontal shift, vertical shift) in scene's coordinates
        """
        mouse_position = self.ui.graphicsView.mapFromGlobal(QCursor.pos())
        if self.ui.graphicsView.rect().contains(mouse_position):
            mouse_over_design_view = self.ui.graphicsView.mapToScene(mouse_position)
        else:
            mouse_over_design_view = None
        if mouse_over_design_view is not None:
            first_item = next(iter(serialized_items.values()))[0]
            x = first_item["x"]
            y = first_item["y"]
            shift_x = x - mouse_over_design_view.x()
            shift_y = y - mouse_over_design_view.y()
        else:
            shift_x = -15.0
            shift_y = -15.0
        return shift_x, shift_y

    @staticmethod
    def _set_deserialized_item_position(item_dict, shift_x, shift_y, scene_rect):
        """Moves item's position by shift_x and shift_y while keeping it within the limits of scene_rect."""
        new_x = np.clip(item_dict["x"] - shift_x, scene_rect.left(), scene_rect.right())
        new_y = np.clip(item_dict["y"] - shift_y, scene_rect.top(), scene_rect.bottom())
        item_dict["x"] = new_x
        item_dict["y"] = new_y

    def _deserialize_items(self, serialized_items):
        """
        Deserializes project items from a dictionary and adds them to the current project.

        Args:
            serialized_items (dict): serialized project items
        """
        if self._project is None:
            return
        scene = self.ui.graphicsView.scene()
        scene.clearSelection()
        shift_x, shift_y = self._deserialized_item_position_shifts(serialized_items)
        scene_rect = scene.sceneRect()
        for category_name, item_dicts in serialized_items.items():
            for item in item_dicts:
                name = item["name"]
                if self.project_item_model.find_item(name) is not None:
                    new_name = self.propose_item_name(name)
                    item["name"] = new_name
                self._set_deserialized_item_position(item, shift_x, shift_y, scene_rect)
                item.pop("short name")
            self._project.add_project_items(category_name, *item_dicts, set_selected=True, verbosity=False)

    @Slot()
    def project_item_to_clipboard(self):
        """Copies the selected project items to system's clipboard."""
        serialized_items = self._serialize_selected_items()
        if not serialized_items:
            return
        item_dump = json.dumps(serialized_items)
        clipboard = QApplication.clipboard()
        data = QMimeData()
        data.setData("application/vnd.spinetoolbox.ProjectItem", QByteArray(item_dump.encode('utf-8')))
        clipboard.setMimeData(data)

    @Slot()
    def project_item_from_clipboard(self):
        """Adds project items in system's clipboard to the current project."""
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        byte_data = mime_data.data("application/vnd.spinetoolbox.ProjectItem")
        if byte_data.isNull():
            return
        item_dump = str(byte_data.data(), "utf-8")
        serialized_items = json.loads(item_dump)
        self._deserialize_items(serialized_items)

    @Slot()
    def duplicate_project_item(self):
        """Duplicates the selected project items."""
        serialized_items = self._serialize_selected_items()
        self._deserialize_items(serialized_items)

    def propose_item_name(self, prefix):
        """
        Proposes a name for a project item.

        The format is `prefix_xx` where `xx` is a counter value [01..99].

        Args:
            prefix (str): a prefix for the name

        Returns:
            a name string
        """
        name_count = self._proposed_item_name_counts.setdefault(prefix, 0)
        name = prefix + " {}".format(name_count + 1)
        if self.project_item_model.find_item(name) is not None:
            if name_count == 98:
                # Avoiding too deep recursions.
                raise RuntimeError("Ran out of numbers: cannot find suitable name for project item.")
            # Increment index recursively if name is already in project.
            self._proposed_item_name_counts[prefix] += 1
            name = self.propose_item_name(prefix)
        return name

    def _item_edit_actions(self):
        """Creates project item edit actions (copy, paste, duplicate) and adds them to proper places."""

        def prepend_to_edit_menu(text, shortcut, slot):
            action = QAction(text, self.ui.graphicsView)
            action.setShortcuts(shortcut)
            action.setShortcutContext(Qt.WidgetShortcut)
            action.triggered.connect(slot)
            self._project_item_actions.append(action)
            self.ui.graphicsView.addAction(action)
            self.ui.menuEdit.insertAction(self.ui.menuEdit.actions()[0], action)
            return action

        self.ui.menuEdit.insertSeparator(self.ui.menuEdit.actions()[0])
        duplicate_action = prepend_to_edit_menu(
            "Duplicate", [QKeySequence(Qt.CTRL + Qt.Key_D)], lambda checked: self.duplicate_project_item()
        )
        paste_action = prepend_to_edit_menu(
            "Paste", QKeySequence.Paste, lambda checked: self.project_item_from_clipboard()
        )
        copy_action = prepend_to_edit_menu("Copy", QKeySequence.Copy, lambda checked: self.project_item_to_clipboard())

        def mirror_action_to_project_tree_view(action_to_duplicate):
            action = QAction(action_to_duplicate.text(), self.ui.treeView_project)
            action.setShortcuts([action_to_duplicate.shortcut()])
            action.setShortcutContext(Qt.WidgetShortcut)
            action.triggered.connect(action_to_duplicate.trigger)
            self._project_item_actions.append(action)
            self.ui.treeView_project.addAction(action)

        mirror_action_to_project_tree_view(copy_action)
        mirror_action_to_project_tree_view(paste_action)
        mirror_action_to_project_tree_view(duplicate_action)

    @Slot(str, str)
    def _show_message_box(self, title, message):
        """Shows an information message box."""
        QMessageBox.information(self, title, message)
