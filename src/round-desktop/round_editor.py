#!/usr/bin/env python3
"""Native plain-text editor for the 1080 px round desktop."""
import codecs
import math
import os
from pathlib import Path
import sys
import tempfile

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango
from round_ui import SHELL_CSS, icon
from round_dock import DockHover

LIMIT = 4 * 1024 * 1024
FILE_ATTRIBUTES = 'standard::type,standard::size,etag::value'
CSS = b'''
#round-shell textview, #round-shell textview text {background:#101012;color:#f5f5f7;font:23px monospace;caret-color:#a3ed75;}
#round-shell textview text selection {background:#385835;}
#round-shell .filename {font:600 31px "Rubik";color:#f5f5f7;}
#round-shell .action {background:#29292e;border-radius:22px;padding:0 14px;font:21px "Rubik";}
#round-shell button.dock-tool {background:transparent;border-radius:24px;padding:0;}
#round-shell button.dock-tool:hover, #round-shell button.dock-tool:focus {background:#39393d;}
#round-shell .save-sheet {background:#1c1c1f;border:1px solid #38383d;border-radius:32px;padding:28px;}
#round-shell .save-sheet .field-label {font:600 17px 'Rubik';color:#b0b0ba;}
#round-shell .save-sheet entry {font:25px 'Rubik';border-radius:16px;background:#29292e;}
#round-shell .save-sheet .location {border-radius:16px;background:#29292e;padding:0 18px;}
#round-shell .save-sheet .location label {font:21px 'Rubik';}
#round-shell .save-sheet .folder-list {background:#242427;border-radius:16px;}
#round-shell .save-sheet .folder-row {border-radius:0;padding:0 16px;}
#round-shell .save-sheet .folder-row label {font:20px 'Rubik';}
#round-shell .save-sheet .action {border-radius:16px;}
#round-shell .save-sheet .accent {background:#a3ed75;color:#182013;}
#round-shell .accent {background:#32442e;color:#c4f5a5;}
'''


def checked_file(path):
    file = Gio.File.new_for_path(str(path))
    info = file.query_info(FILE_ATTRIBUTES, Gio.FileQueryInfoFlags.NONE, None)
    if info.get_file_type() != Gio.FileType.REGULAR or info.get_size() > LIMIT:
        raise ValueError('Choose a regular text file up to 4 MiB.')
    return file, info.get_attribute_string('etag::value')


def read_text(path):
    file, _ = checked_file(path)
    _, data, etag = file.load_contents(None)
    if len(data) > LIMIT or b'\x00' in data:
        raise ValueError('Choose a UTF-8 text file up to 4 MiB.')
    bom = data.startswith(codecs.BOM_UTF8)
    value = data.decode('utf-8-sig')
    # Preserve mixed line endings verbatim. Normalize uniform files for editing.
    newline = '\n'
    if '\r' in value:
        if '\n' not in value:
            newline = '\r'
        elif '\r' not in value.replace('\r\n', '') and '\n' not in value.replace('\r\n', ''):
            newline = '\r\n'
    return value.replace(newline, '\n'), etag, bom, newline


def write_text(path, value, etag, bom, newline):
    data = value.replace('\n', newline).encode('utf-8-sig' if bom else 'utf-8')
    if len(data) > LIMIT:
        raise ValueError('This document exceeds the 4 MiB limit.')
    if etag is None:
        # Publish the complete file only if the chosen name is still available.
        with tempfile.NamedTemporaryFile(dir=path.parent) as staged:
            staged.write(data)
            staged.flush()
            os.link(staged.name, path)
        return checked_file(path)[1]
    file, current = checked_file(path)
    if current != etag:
        raise ValueError('The file changed on disk. Use Save As to keep your edits.')
    _, result = file.replace_contents(data, etag, False, Gio.FileCreateFlags.NONE, None)
    return result


def button(name, action, symbol=None, accent=False):
    widget = Gtk.Button()
    widget.get_style_context().add_class('action')
    if accent:
        widget.get_style_context().add_class('accent')
    if symbol:
        widget.add(icon(symbol, 25))
    else:
        widget.set_label(name)
    widget.set_tooltip_text(name)
    widget.get_accessible().set_name(name)
    widget.set_size_request(58, 56)
    widget.connect('clicked', lambda _: action())
    return widget


class Document(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Text Editor · AroundOS')
        self.path, self.etag, self.bom, self.newline = None, None, False, '\n'
        self.set_name('round-shell')
        self.set_decorated(False)
        self.set_default_size(1080, 1080)
        self.connect('delete-event', self.close_request)
        self.connect('key-press-event', self.key)
        self.stack = Gtk.Stack()
        self.stack.set_homogeneous(False)
        self.add(self.stack)
        page = Gtk.Fixed()
        self.stack.add_named(page, 'document')
        self.heading = Gtk.Label()
        self.heading.get_style_context().add_class('filename')
        self.heading.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.heading.set_size_request(536, 54)
        page.put(self.heading, 272, 126)
        self.tools = []
        dock = Gtk.Image.new_from_file(str(Path(__file__).with_name('editor-dock.svg')))
        dock.set_size_request(416, 120)
        page.put(dock, 332, 936)
        for index, (name, action, symbol) in enumerate([
                ('New document', lambda: Document(app).present(), 'document-new-symbolic'),
                ('Open file', lambda: self.choose(False), 'document-open-symbolic'),
                ('Save', self.save, 'document-save-symbolic'),
                ('Save As', lambda: self.choose(True), 'document-save-as-symbolic'),
                ('Close', self.close, 'window-close-symbolic')]):
            tool = button(name, action, symbol)
            tool.get_style_context().add_class('dock-tool')
            tool.set_size_request(56, 56)
            x = 404 + 68 * index
            y = round(540 + math.sqrt(476**2 - (x - 540)**2))
            page.put(tool, x - 28, y - 28)
            self.tools.append(tool)
        DockHover(page, self.tools)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_pixels_below_lines(3)
        self.view.get_accessible().set_name('Document text')
        self.buffer = self.view.get_buffer()
        self.buffer.connect('modified-changed', self.update_title)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.view)
        scroll.set_size_request(776, 640)
        page.put(scroll, 152, 210)
        self.update_title()
        self.fullscreen()
        self.show_all()
        self.view.grab_focus()

    def update_title(self, *_):
        name = self.path.name if self.path else 'Untitled'
        self.heading.set_text(name + ('  •' if self.buffer.get_modified() else ''))
        self.heading.set_tooltip_text(str(self.path or name))

    def panel(self, title):
        self.document()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_size_request(580, -1)
        heading = Gtk.Label(label=title)
        heading.get_style_context().add_class('filename')
        box.add(heading)
        self.stack.add_named(box, 'panel')
        box.show()
        self.stack.set_visible_child(box)
        return box

    def document(self):
        self.stack.set_visible_child_name('document')
        panel = self.stack.get_child_by_name('panel')
        if panel:
            panel.destroy()
        self.view.grab_focus()

    def message(self, title, detail, actions):
        box = self.panel(title)
        note = Gtk.Label(label=detail)
        note.set_line_wrap(True)
        note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        note.set_max_width_chars(42)
        note.get_style_context().add_class('secondary')
        box.add(note)
        for name, action in actions:
            box.add(button(name, action))
        box.show_all()
        box.get_children()[2].grab_focus()

    def error(self, exc):
        self.message('File could not be used', str(exc), [('Back to document', self.document)])

    def load(self, path):
        try:
            value, etag, bom, newline = read_text(path)
        except (OSError, ValueError, GLib.Error) as exc:
            self.error(exc)
            return
        self.path, self.etag, self.bom, self.newline = path, etag, bom, newline
        self.buffer.set_text(value)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.buffer.set_modified(False)
        self.update_title()
        self.document()

    def save_sheet(self, after):
        folder = self.path.parent if self.path else Path.home()
        filename = self.path.name if self.path else 'Untitled.txt'

        def sheet(title):
            box = self.panel(title)
            box.get_style_context().add_class('save-sheet')
            box.get_children()[0].set_xalign(0)
            return box

        def field(box, name):
            label = Gtk.Label(label=name, xalign=0)
            label.get_style_context().add_class('field-label')
            box.add(label)

        def row(name, symbol, action, style):
            widget = Gtk.Button()
            widget.set_size_request(-1, 62)
            widget.get_style_context().add_class(style)
            widget.get_accessible().set_name(name)
            widget.connect('clicked', lambda _: action())
            line = Gtk.Box(spacing=14)
            line.add(icon(symbol, 24))
            caption = Gtk.Label(label=name, xalign=0)
            caption.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            caption.set_max_width_chars(27)
            line.pack_start(caption, True, True, 0)
            line.add(icon('go-next-symbolic', 18))
            widget.add(line)
            return widget

        def actions(box, back, accept, action):
            buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, homogeneous=True)
            buttons.set_margin_top(8)
            confirm = button(accept, action, accent=True)
            buttons.add(confirm)
            buttons.add(button('Cancel', back))
            box.add(buttons)
            return confirm

        def browse(target):
            nonlocal folder
            try:
                dirs = sorted((p for p in target.iterdir() if not p.name.startswith('.') and p.is_dir()),
                              key=lambda p: p.name.casefold())
            except OSError as exc:
                self.message('Cannot open folder', str(exc), [('Back', form)])
                return
            box = sheet('Choose folder')
            header = Gtk.Box(spacing=12)
            parent = button('Parent folder', lambda: browse(target.parent), 'go-up-symbolic')
            parent.set_sensitive(target != target.parent)
            header.add(parent)
            location = Gtk.Label(label=target.as_posix(), xalign=0)
            location.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            location.set_max_width_chars(30)
            location.get_style_context().add_class('secondary')
            header.pack_start(location, True, True, 0)
            box.add(header)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_size_request(-1, 248)
            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            rows.get_style_context().add_class('folder-list')
            for child in dirs:
                rows.add(row(child.name, 'folder-symbolic', lambda p=child: browse(p), 'folder-row'))
            if not dirs:
                rows.add(Gtk.Label(label='No subfolders', margin=20))
            scroll.add(rows)
            box.add(scroll)

            def select():
                nonlocal folder
                folder = target
                form()

            actions(box, form, 'Use this folder', select)
            box.show_all()

        def form():
            box = sheet('Save As')
            field(box, 'File name')
            entry = Gtk.Entry()
            entry.set_size_request(-1, 62)
            entry.set_text(filename)
            entry.get_accessible().set_name('File name')
            box.add(entry)
            field(box, 'Save in')
            name = 'Home' if folder == Path.home() else str(folder)
            destination = row(name, 'folder-symbolic', lambda: browse(folder), 'location')
            box.add(destination)

            def submit():
                if not filename:
                    return
                path = folder / Path(filename).expanduser()
                if path.is_dir():
                    browse(path)
                    return
                self.save_as(path, after, form)

            save = actions(box, self.document, 'Save', submit)
            def changed(widget):
                nonlocal filename
                filename = widget.get_text()
                save.set_sensitive(bool(filename.strip()))

            entry.connect('changed', changed)
            entry.connect('activate', lambda _: save.clicked() if save.get_sensitive() else None)
            changed(entry)
            box.show_all()
            entry.grab_focus()
            entry.select_region(0, len(Path(filename).stem))

        form()

    def choose(self, saving, after=None):
        if saving:
            self.save_sheet(after)
            return
        folder = self.path.parent if self.path else Path.home()
        box = self.panel('Open File')
        entry = Gtk.Entry()
        entry.set_placeholder_text('Filename or path')
        entry.get_accessible().set_name('Filename or path')
        box.add(entry)
        directory = Gtk.Label()
        directory.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        directory.set_max_width_chars(36)
        directory.get_style_context().add_class('secondary')
        box.add(directory)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_size_request(-1, 204)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll.add(rows)
        box.add(scroll)

        def browse(target):
            nonlocal folder
            try:
                items = sorted((p for p in target.iterdir() if not p.name.startswith('.')),
                               key=lambda p: (not p.is_dir(), p.name.casefold()))
            except OSError as exc:
                self.error(exc)
                return
            folder = target
            directory.set_text(str(folder))
            for row in rows.get_children():
                row.destroy()
            for p in [folder.parent, *items]:
                parent = p == folder.parent
                row = button('Parent folder' if parent else p.name,
                             lambda path=p: browse(path) if path.is_dir() else entry.set_text(path.name))
                caption = row.get_child()
                caption.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                caption.set_max_width_chars(32)
                if not parent and p.is_dir():
                    caption.set_text(p.name + '/')
                rows.add(row)
            rows.show_all()

        def submit():
            if not entry.get_text():
                entry.grab_focus()
                return
            path = folder / Path(entry.get_text()).expanduser()
            if path.is_dir():
                browse(path)
                entry.set_text('')
            elif self.buffer.get_modified():
                # Open in a separate window so this draft stays available.
                child = Document(self.get_application())
                self.document()
                child.load(path)
                child.present()
            else:
                self.load(path)

        entry.connect('activate', lambda _: submit())
        actions = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        actions.add(button('Cancel', self.document))
        actions.add(button('Open', submit, accent=True))
        box.add(actions)
        browse(folder)
        box.show_all()

    def save_as(self, path, after, back=None):
        if path == self.path:
            self.save(after)
            return
        try:
            if path.exists():
                _, etag = checked_file(path)
                self.message('Replace this file?', str(path), [
                    ('Cancel', back or self.document), ('Replace', lambda: self.store(path, etag, after))])
            else:
                self.store(path, None, after)
        except (OSError, ValueError, GLib.Error) as exc:
            self.error(exc)

    def store(self, path, etag, after):
        value = self.buffer.get_text(*self.buffer.get_bounds(), True)
        try:
            new_etag = write_text(path, value, etag, self.bom, self.newline)
        except (OSError, ValueError, GLib.Error) as exc:
            self.error(exc)
            return
        self.path, self.etag = path, new_etag
        self.buffer.set_modified(False)
        self.update_title()
        self.document()
        if after:
            after()

    def save(self, after=None):
        if self.path:
            self.store(self.path, self.etag, after)
        else:
            self.choose(True, after)

    def close_request(self, *_):
        if not self.buffer.get_modified():
            return False
        self.message('Save your changes?', self.path.name if self.path else 'Untitled', [
            ('Keep editing', self.document), ('Save and close', lambda: self.save(self.destroy)),
            ('Discard changes', self.destroy)])
        return True

    def key(self, _, event):
        if self.stack.get_visible_child_name() == 'panel':
            if event.keyval == Gdk.KEY_Escape:
                self.document()
                return True
            return False
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        key = Gdk.keyval_to_lower(event.keyval)
        if mods == Gdk.ModifierType.CONTROL_MASK:
            action = {Gdk.KEY_s: self.save, Gdk.KEY_o: lambda: self.choose(False),
                      Gdk.KEY_w: self.close}.get(key)
            if action:
                action()
                return True
        if mods == (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK) and key == Gdk.KEY_s:
            self.choose(True)
            return True
        return False


class Editor(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.aroundos.Editor', flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_data(SHELL_CSS + CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 900)

    def do_activate(self):
        window = self.get_active_window() or Document(self)
        window.present()

    def do_open(self, files, count, hint):
        for file in files:
            path = Path(file.get_path()) if file.get_path() else None
            existing = next((w for w in self.get_windows() if path and w.path == path), None)
            if existing:
                existing.present()
                continue
            window = Document(self)
            if path:
                window.load(path)
            else:
                window.error('Choose a local file.')
            window.present()


if __name__ == '__main__':
    GLib.set_prgname('aroundos-editor')
    sys.exit(Editor().run(sys.argv))
