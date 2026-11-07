#!/usr/bin/env python3
"""Native, circular file navigation for AroundOS. Uses GIO; never executes filenames."""
import argparse
import json
import math
import os
from pathlib import Path
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from round_dock import DockHover
from round_ui import MENU_CSS, icon as symbol_image, symbol_pixbuf

USER_HOME = Path.home()
CSS = b"""
#round-files { background: #101012; color: #f1f4f6; }
#round-files * { transition: none; animation: none; box-shadow: none; text-shadow: none; }
#round-files button { background: transparent; background-image: none; border: 1px solid transparent;
    border-radius: 24px; padding: 0; min-width: 0; min-height: 0; color: #e8edf0; }
#round-files button:hover, #round-files button:focus { background: #23332d; border-color: #8cbb62; }
#round-files button:active { background: #31462d; border-color: #b1ef71; }
#round-files button:disabled { color: #64717a; }
#round-files .control { background: #242426; border-color: transparent; border-radius: 50%; }
#round-files button.dock-tool { background: transparent; border-radius: 24px; }
#round-files button.dock-tool:hover, #round-files button.dock-tool:focus { background: #39393d; }
#round-files button.dock-tool:active { background: #344d31; border-color: #a3ed75; }
#round-files .control label { font: 25px 'Rubik'; }
#round-files button.selected { background: #293b28; border: 1px solid #8bc66a; color: #b1ef71; }
#round-files .file-tile { border-radius: 24px; }
#round-files .file-tile:disabled, #round-files .file-row:disabled { opacity: 0.22; }
#round-files .file-name { font: 26px 'Rubik'; color: #f1f4f6; }
#round-files .file-row .file-name { font-size: 25px; }
#round-files .detail { font: 17px 'Rubik'; color: #9cabb2; }
#round-files .path { background: #202023; border: 1px solid transparent; border-radius: 38px; padding: 0 24px; }
#round-files .path label { font: 28px 'Rubik'; color: #f1f4f6; }

#round-files .notice { font: 26px 'Rubik'; color: #c8d6cc; }
#round-files entry { background: #202023; color: #f1f4f6; border: 2px solid #a3e66a;
    border-radius: 38px; padding: 0 22px; font: 28px 'Rubik'; min-height: 0; }
""" + MENU_CSS


def folder_pixbuf(kind):
    return symbol_pixbuf("folder.fill.blue",128) or Gtk.IconTheme.get_default().load_icon("folder",128,0)


def readable_size(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class RoundFiles(Gtk.Application):
    def __init__(self, location, audit=None):
        super().__init__(application_id="org.aroundos.RoundFiles", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.initial_location = location
        self.audit_path = audit
        self.window = None
        self.entries = []
        self.history = []
        self.future = []
        self.view_mode = "grid"
        self.query = ""
        self.filtered_entries = []
        self.search_visible = False
        self.location = None
        self.sort_recent = False
        self.cancellable = None
        self.generation = 0
        self.monitor = None
        self.refresh_source = None
        self.layout_source = None
        self.placed = []
        self.row_widgets = []
        self.options = None
        self.diagnostic = ""
        self.loading = False
        self.geometry_cache = {}
        self.dock_plate = None
        self.dock_buttons = []
        self.dock_hover = None
        self.view_icon = None

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title="Files · AroundOS")
        self.window.set_name("round-files")
        self.window.set_decorated(False)
        self.window.set_default_size(1080, 1080)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 900)
        self.window.connect("key-press-event", self.key)
        self.window.connect("destroy", self.cleanup)
        overlay = Gtk.Overlay()
        self.window.add(overlay)
        self.content = Gtk.Fixed()
        overlay.add(self.content)
        self.fixed = Gtk.Fixed()
        overlay.add_overlay(self.fixed)
        overlay.set_overlay_pass_through(self.fixed, True)
        self.fixed.connect("size-allocate", self.schedule_layout)
        self.places = [
            ("Home", "user-home-symbolic", USER_HOME),
            ("Downloads", "folder-download-symbolic", self.user_directory(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")),
            ("Documents", "folder-documents-symbolic", self.user_directory(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents")),
            ("Pictures", "folder-pictures-symbolic", self.user_directory(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures")),
            ("Music", "folder-music-symbolic", self.user_directory(GLib.UserDirectory.DIRECTORY_MUSIC, "Music")),
            ("Computer", "drive-harddisk-symbolic", Path("/")),
        ]
        self.place_widgets = []
        self.main_controls = []
        self.search_button = self.control("Search this folder", "system-search-symbolic", lambda _: self.toggle_search(), 230, 172, 76, 76)
        self.sort_button = self.control("Sort by name", "view-sort-ascending-symbolic", lambda _: self.toggle_sort(), 774, 172, 76, 76)
        self.path_button = Gtk.Button()
        self.path_button.get_style_context().add_class("path")
        self.path_button.get_accessible().set_name("Folder shortcuts")
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        path_icon = symbol_image("user-home-symbolic",34)
        path_icon.set_pixel_size(34)
        path_box.pack_start(path_icon, False, False, 0)
        self.path_label = self.label("", "path-text")
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.path_label.set_max_width_chars(1)
        path_box.pack_start(self.path_label, True, True, 0)
        path_arrow = symbol_image("pan-down-symbolic",28)
        path_arrow.set_pixel_size(28)
        path_box.pack_end(path_arrow, False, False, 0)
        self.path_button.add(path_box)
        self.path_button.connect("clicked", lambda _: self.toggle_places())
        self.put(self.path_button, 326, 172, 428, 76)
        self.main_controls.append(self.path_button)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search this folder")
        self.search_entry.get_accessible().set_name("Search this folder")
        self.search_entry.connect("search-changed", self.search_changed)
        self.search_entry.connect("stop-search", lambda _: self.toggle_search(False))
        self.search_entry.connect("activate", lambda _: self.hide_keyboard())
        self.put(self.search_entry, 326, 172, 428, 76)
        self.main_controls.append(self.search_entry)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.file_grid = Gtk.Grid()
        self.file_grid.set_row_spacing(8)
        self.file_grid.set_column_spacing(12)
        self.file_grid.set_column_homogeneous(True)
        self.file_grid.set_margin_bottom(8)
        self.scroller.add(self.file_grid)
        self.content.put(self.scroller, 120, 276)
        self.placed.append((self.scroller, (120, 276, 840, 678)))
        # Paint the curved plate below the buttons on their overlay.
        self.dock_plate = Gtk.Image()
        self.dock_art = GdkPixbuf.Pixbuf.new_from_file(str(Path(__file__).with_name("files-dock.svg")))
        self.put(self.dock_plate, 370, 962, 340, 88)
        self.back_button = self.dock_control(0, "Back", "go-previous-symbolic", lambda _: self.go_back())
        self.forward_button = self.dock_control(1, "Forward", "go-next-symbolic", lambda _: self.go_forward())
        self.up_button = self.dock_control(2, "Parent folder", "go-up-symbolic", lambda _: self.go_up())
        self.view_button = self.dock_control(3, "Switch to list view", "view-list-symbolic",
                                             lambda _: self.set_view("list" if self.view_mode == "grid" else "grid"))
        self.close_button = self.dock_control(4, "Close Files", "window-close-symbolic", lambda _: self.window.close())
        self.dock_hover = DockHover(self.fixed, self.dock_buttons)
        self.notice = self.label("", "notice")
        self.notice.set_line_wrap(True)
        self.notice.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.notice.set_max_width_chars(1)
        self.notice.set_lines(6)
        self.notice.set_ellipsize(Pango.EllipsizeMode.END)
        self.notice.set_justify(Gtk.Justification.CENTER)
        self.notice.set_xalign(0.5)
        self.put(self.notice, 250, 470, 580, 250)
        self.window.show_all()
        self.window.maximize()
        self.search_entry.hide()
        self.navigate(Gio.File.new_for_path(self.initial_location))
        if self.audit_path:
            GLib.timeout_add_seconds(3, self.audit)

    @staticmethod
    def user_directory(kind, fallback):
        return Path(GLib.get_user_special_dir(kind) or USER_HOME / fallback)

    @staticmethod
    def label(text, style):
        result = Gtk.Label(label=text, xalign=0)
        result.get_style_context().add_class(style)
        return result

    def button(self, text, icon, callback, style=None, accessible=None):
        result = Gtk.Button()
        if style:
            result.get_style_context().add_class(style)
        result.get_accessible().set_name(accessible or text or "")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        if icon:
            image = symbol_image(icon,32 if text else 34)
            image.set_pixel_size(32 if text else 34)
            box.pack_start(image, False, False, 0)
        if text:
            result.text_widget = Gtk.Label(label=text)
            box.pack_start(result.text_widget, False, False, 0)
        result.add(box)
        result.connect("clicked", callback)
        return result

    def control(self, name, icon, callback, x, y, width, height, icon_size=34):
        result = self.button(None, icon, callback, "control", accessible=name)
        image = result.get_child().get_children()[0]
        pixbuf = symbol_pixbuf(icon, icon_size)
        if pixbuf: image.set_from_pixbuf(pixbuf)
        else: image.set_pixel_size(icon_size)
        self.put(result, x, y, width, height)
        self.main_controls.append(result)
        return result

    def dock_control(self, index, name, icon, callback):
        x = 404 + index * 68
        y = round(540 + math.sqrt(476**2 - (x - 540)**2))
        button = Gtk.Button()
        button.get_accessible().set_name(name)
        button.add(symbol_image(icon, 34))
        button.get_style_context().add_class("dock-tool")
        button.connect("clicked", callback)
        self.put(button, x - 28, y - 28, 56, 56)
        self.main_controls.append(button)
        self.dock_buttons.append(button)
        return button

    def set_view(self, mode):
        self.view_mode = mode
        self.scroller.get_vadjustment().set_value(0)
        self.render()

    def toggle_sort(self):
        self.sort_recent = not self.sort_recent
        self.sort_entries()
        self.scroller.get_vadjustment().set_value(0)
        self.render()

    def sort_entries(self):
        self.entries.sort(key=lambda info: (
            info.get_file_type() != Gio.FileType.DIRECTORY,
            -info.get_attribute_uint64("time::modified") if self.sort_recent else info.get_display_name().casefold()))

    def toggle_search(self, visible=None):
        if self.options:
            self.toggle_places()
        self.search_visible = not self.search_visible if visible is None else visible
        self.path_button.set_visible(not self.search_visible)
        self.search_entry.set_visible(self.search_visible)
        if self.search_visible:
            self.search_entry.grab_focus()
        else:
            self.search_entry.set_text("")
            self.query = ""
            self.hide_keyboard()
        self.render()

    def search_changed(self, entry):
        self.query = entry.get_text().casefold().strip()
        self.scroller.get_vadjustment().set_value(0)
        self.render()

    @staticmethod
    def hide_keyboard():
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            connection.call("sm.puri.OSK0", "/sm/puri/OSK0", "sm.puri.OSK0", "SetVisible",
                            GLib.Variant("(b)", (False,)), None, Gio.DBusCallFlags.NONE, 1000, None, None, None)
        except GLib.Error:
            pass

    def put(self, widget, x, y, width, height):
        self.fixed.put(widget, int(x), int(y))
        self.placed.append((widget, (x, y, width, height)))
        self.layout()

    def schedule_layout(self, *_):
        if self.layout_source is None:
            self.layout_source = GLib.idle_add(self.layout)

    def layout(self):
        self.layout_source = None
        width, height = self.fixed.get_allocated_width(), self.fixed.get_allocated_height()
        scale = min(width, height) / 1080 if min(width, height) > 1 else 1
        ox, oy = max(0, (width - 1080 * scale) / 2), max(0, (height - 1080 * scale) / 2)
        dock_changed = False
        for widget, (x, y, w, h) in self.placed:
            geometry = (round(ox + x * scale), round(oy + y * scale), round(w * scale), round(h * scale))
            if self.geometry_cache.get(widget) != geometry:
                dock_changed |= widget in self.dock_buttons
                if widget is self.dock_plate:
                    widget.set_from_pixbuf(self.dock_art.scale_simple(max(1, geometry[2]), max(1, geometry[3]), GdkPixbuf.InterpType.BILINEAR))
                self.geometry_cache[widget] = geometry
                widget.get_parent().move(widget, geometry[0], geometry[1])
                widget.set_size_request(geometry[2], geometry[3])
        if dock_changed and self.dock_hover:
            bounds = [self.geometry_cache[button] for button in self.dock_buttons]
            self.dock_hover.centers = [(x + w // 2, y + h // 2) for x, y, w, h in bounds]
            self.dock_hover.scale = scale
            self.dock_hover.update(None, None, reset=True)
        return False

    def navigate(self, location, remember=True, preserve_scroll=False):
        if self.options:
            self.toggle_places()
        if self.refresh_source:
            GLib.source_remove(self.refresh_source)
            self.refresh_source = None
        if remember and self.location and not location.equal(self.location):
            self.history.append(self.location)
            self.future.clear()
        if not preserve_scroll and self.search_visible:
            self.toggle_search(False)
        self.location = location
        if not preserve_scroll:
            self.scroller.get_vadjustment().set_value(0)
        self.generation += 1
        generation = self.generation
        if self.cancellable:
            self.cancellable.cancel()
        self.cancellable = Gio.Cancellable()
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        self.entries = []
        self.diagnostic = ""
        self.loading = True
        self.path_label.set_text(location.get_parse_name())
        self.back_button.set_sensitive(bool(self.history))
        self.forward_button.set_sensitive(bool(self.future))
        self.up_button.set_sensitive(location.get_parent() is not None)
        if not preserve_scroll:
            self.render()
        location.enumerate_children_async(
            "standard::name,standard::display-name,standard::type,standard::size,standard::is-hidden,standard::icon,time::modified",
            Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, self.cancellable,
            self.enumerated, generation)

    def enumerated(self, source, result, generation):
        try:
            enumerator = source.enumerate_children_finish(result)
            if generation != self.generation:
                enumerator.close_async(GLib.PRIORITY_DEFAULT, None, None, None)
                return
            enumerator.next_files_async(128, GLib.PRIORITY_DEFAULT, self.cancellable, self.batch, generation)
        except GLib.Error as error:
            if generation == self.generation:
                self.fail(error.message)

    def batch(self, enumerator, result, generation):
        try:
            batch = enumerator.next_files_finish(result)
            if generation != self.generation:
                enumerator.close_async(GLib.PRIORITY_DEFAULT, None, None, None)
                return
            for info in batch:
                if not info.get_is_hidden():
                    self.entries.append(info)
            if batch:
                enumerator.next_files_async(128, GLib.PRIORITY_DEFAULT, self.cancellable, self.batch, generation)
                return
            enumerator.close_async(GLib.PRIORITY_DEFAULT, None, None, None)
            self.loading = False
            self.sort_entries()
            try:
                self.monitor = self.location.monitor_directory(Gio.FileMonitorFlags.NONE, None)
                self.monitor.connect("changed", self.changed)
            except GLib.Error:
                pass
            self.render()
        except GLib.Error as error:
            if generation == self.generation:
                self.fail(error.message)

    def changed(self, *_):
        if self.refresh_source:
            GLib.source_remove(self.refresh_source)
        self.refresh_source = GLib.timeout_add(500, self.refresh)

    def refresh(self):
        self.refresh_source = None
        if self.window and self.location:
            self.navigate(self.location, remember=False, preserve_scroll=True)
        return False

    def fail(self, message):
        self.loading = False
        self.diagnostic = "Couldn’t open this folder.\n" + message
        self.render()

    def render(self):
        for widget in self.row_widgets:
            self.file_grid.remove(widget)
        self.row_widgets = []
        self.filtered_entries = [info for info in self.entries if self.query in info.get_display_name().casefold()]
        sort_label = "Sorted by most recent; sort by name" if self.sort_recent else "Sorted by name; sort by most recent"
        self.sort_button.get_accessible().set_name(sort_label)
        self.sort_button.set_tooltip_text(sort_label)
        view_label = "Switch to list view" if self.view_mode == "grid" else "Switch to grid view"
        self.view_button.get_accessible().set_name(view_label)
        view_icon = "view-list-symbolic" if self.view_mode == "grid" else "view-grid-symbolic"
        if self.view_icon != view_icon:
            self.view_icon = view_icon
            image = self.view_button.get_child()
            pixbuf = symbol_pixbuf(view_icon, 34)
            if pixbuf:
                image.set_from_pixbuf(pixbuf)
            else:
                image.set_from_icon_name(view_icon, Gtk.IconSize.DIALOG)
            image.set_pixel_size(34)
            self.dock_hover.art[self.dock_buttons.index(self.view_button)] = (pixbuf, 34)
        for button, active in ((self.sort_button, self.sort_recent),
                               (self.search_button, self.search_visible)):
            style = button.get_style_context()
            style.add_class("selected") if active else style.remove_class("selected")
        text = self.diagnostic or ("Loading…" if self.loading else "No matching files" if self.query and not self.filtered_entries else "This folder is empty" if not self.entries else "")
        self.notice.set_text(text)
        self.notice.set_visible(bool(text))
        self.scroller.set_visible(not text)
        visible = [] if text else self.filtered_entries
        for index, info in enumerate(visible):
            tile = self.view_mode == "grid"
            row = Gtk.Button()
            row.get_style_context().add_class("file-tile" if tile else "file-row")
            row.get_accessible().set_name(info.get_display_name())
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if tile else Gtk.Orientation.HORIZONTAL, spacing=6 if tile else 18)
            box.set_valign(Gtk.Align.CENTER)
            if not tile:
                box.set_margin_start(16)
                box.set_margin_end(16)
            if info.get_file_type() == Gio.FileType.DIRECTORY:
                kind = info.get_name() if self.location.get_path() == str(USER_HOME) else ""
                pixbuf = folder_pixbuf(kind)
                if not tile:
                    pixbuf = pixbuf.scale_simple(56, 49, GdkPixbuf.InterpType.BILINEAR)
                icon = Gtk.Image.new_from_pixbuf(pixbuf)
            else:
                icon = Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)
                icon.set_pixel_size(104 if tile else 46)
            box.pack_start(icon, False, False, 0)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            texts.set_valign(Gtk.Align.CENTER)
            name = self.label(info.get_display_name(), "file-name")
            name.set_ellipsize(Pango.EllipsizeMode.END if tile else Pango.EllipsizeMode.MIDDLE)
            name.set_max_width_chars(1)
            if tile:
                name.set_line_wrap(True)
                name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                name.set_lines(2)
                name.set_xalign(0.5)
                name.set_justify(Gtk.Justification.CENTER)
                name.set_size_request(-1, 64)
            texts.pack_start(name, False, False, 0)
            if not tile:
                modified = time.strftime("%d %b", time.localtime(info.get_attribute_uint64("time::modified")))
                detail = "Folder" if info.get_file_type() == Gio.FileType.DIRECTORY else readable_size(info.get_size())
                texts.pack_start(self.label(f"{detail}  ·  {modified}", "detail"), False, False, 0)
            box.pack_start(texts, not tile, not tile, 0)
            row.add(box)
            row.connect("clicked", lambda _, item=info: self.open_item(item))
            row.set_sensitive(self.options is None)
            columns = 4 if tile else 1
            row.set_hexpand(True)
            row.set_size_request(-1, 186 if tile else 72)
            self.file_grid.attach(row, index % columns, index // columns, 1, 1)
            self.row_widgets.append(row)
            row.show_all()
        self.layout()

    def open_item(self, info):
        target = self.location.get_child(info.get_name())
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            self.navigate(target)
        else:
            Gio.AppInfo.launch_default_for_uri_async(target.get_uri(), self.window.get_display().get_app_launch_context(), None, self.opened, None)

    def opened(self, source, result, _):
        try:
            Gio.AppInfo.launch_default_for_uri_finish(result)
        except GLib.Error as error:
            self.fail(error.message)

    def go_back(self):
        if self.history:
            self.future.append(self.location)
            self.navigate(self.history.pop(), remember=False)

    def go_forward(self):
        if self.future:
            self.history.append(self.location)
            self.navigate(self.future.pop(), remember=False)

    def go_up(self):
        if self.location and self.location.get_parent():
            self.navigate(self.location.get_parent())

    def key(self, _, event):
        if event.keyval == Gdk.KEY_Escape and self.options:
            self.toggle_places()
            return True
        if event.keyval == Gdk.KEY_Escape and self.search_visible:
            self.toggle_search(False)
            return True
        if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_f:
            self.toggle_search(True)
            return True
        if event.state & Gdk.ModifierType.MOD1_MASK and event.keyval == Gdk.KEY_Right:
            self.go_forward()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        if event.state & Gdk.ModifierType.MOD1_MASK and event.keyval == Gdk.KEY_Left:
            self.go_back()
            return True
        return False

    def toggle_places(self):
        if self.options:
            old = self.options
            self.options = None
            self.place_widgets = []
            self.geometry_cache.pop(old, None)
            self.placed = [(w, b) for w, b in self.placed if w != old]
            self.fixed.remove(old)
            for widget in self.row_widgets + self.main_controls:
                widget.set_sensitive(True)
            self.back_button.set_sensitive(bool(self.history))
            self.forward_button.set_sensitive(bool(self.future))
            self.up_button.set_sensitive(self.location.get_parent() is not None)
            self.render()
            return
        self.hide_keyboard()
        for widget in self.row_widgets + self.main_controls:
            widget.set_sensitive(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("action-menu")
        self.options = box
        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        for i, (label, icon, path) in enumerate(self.places):
            button = self.button(label, icon, lambda _, p=path: self.navigate(Gio.File.new_for_path(str(p))))
            button.set_hexpand(True)
            button.set_vexpand(True)
            grid.attach(button, i % 2, i // 2, 1, 1)
            self.place_widgets.append(button)
        box.pack_start(grid, True, True, 0)
        box.pack_end(self.button("Done", "object-select-symbolic", lambda _: self.toggle_places()), False, False, 0)
        self.put(box, 260, 266, 560, 548)
        box.show_all()

    def audit(self):
        allocation = self.window.get_allocation()
        centre = (allocation.width / 2, allocation.height / 2)
        radius = min(allocation.width, allocation.height) / 2
        result = {"window": [allocation.width, allocation.height], "location": self.location.get_uri(), "items": len(self.entries), "view": self.view_mode, "outside_circle": [], "widgets": []}
        for widget, _ in self.placed:
            if widget == self.scroller or not widget.get_visible():
                continue
            a = widget.get_allocation()
            x, y = widget.translate_coordinates(self.window, 0, 0)
            r = max(math.hypot(px - centre[0], py - centre[1]) for px in (x, x + a.width) for py in (y, y + a.height))
            record = {"name": widget.get_accessible().get_name(), "bounds": [x, y, a.width, a.height], "radius": round(r, 2)}
            result["widgets"].append(record)
            if r > radius:
                result["outside_circle"].append(record)
        Path(self.audit_path).write_text(json.dumps(result, indent=2))
        return False

    def cleanup(self, *_):
        self.generation += 1
        if self.cancellable:
            self.cancellable.cancel()
        if self.monitor:
            self.monitor.cancel()
        if self.refresh_source:
            GLib.source_remove(self.refresh_source)
        self.window = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("location", nargs="?", default=str(USER_HOME))
    parser.add_argument("--audit")
    args = parser.parse_args()
    GLib.set_prgname("aroundos-round-files")
    RoundFiles(os.path.abspath(args.location), args.audit).run([])
