#!/usr/bin/env python3
"""Check live editor geometry, file dispatch and save behavior with disposable files."""
import codecs
import math
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
from round_editor import Editor, Gio, GLib, Gtk
from round_files import RoundFiles
from round_shell import Shell


def wait(condition):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if condition():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for the live desktop')


def inside(window, widget):
    x, y = widget.translate_coordinates(window, 0, 0)
    a = widget.get_allocation()
    assert max(math.hypot(px-540, py-540) for px in (x, x+a.width)
               for py in (y, y+a.height)) <= 520, (x, y, a.width, a.height)


def check(root):
    app = Editor()
    assert app.register(None) and not app.get_is_remote(), 'Close the editor before testing.'
    launcher = Shell('launchpad')
    launcher.collect_apps()
    editors = [item for item in launcher.apps if item['name'] == 'Text Editor']
    assert len(editors) == 1 and editors[0]['app'].get_id() == 'aroundos-editor.desktop'
    assert not any(item['name'].casefold() in ('mousepad', 'text editor settings') for item in launcher.apps)
    editors[0]['app'].launch([], None)
    wait(lambda: app.get_windows())
    win = app.get_windows()[0]
    wait(lambda: win.get_allocated_width() == win.get_allocated_height() == 1080)
    inside(win, win.view)
    assert len(win.tools) == 6
    for control in win.tools:
        assert control.translate_coordinates(win, 0, 0)[1] >= 936
        inside(win, control)
    win.buffer.set_text('unsaved draft')
    win.buffer.set_modified(True)
    win.close()
    wait(lambda: win.stack.get_visible_child_name() == 'panel')
    win.document()
    file = root / 'Draft — 01.txt'
    file.write_bytes(codecs.BOM_UTF8 + 'café\r\n'.encode())
    opener = subprocess.Popen([sys.executable, __file__, '--open-fixture', str(file)])
    try:
        wait(lambda: any(w.path == file for w in app.get_windows()) or opener.poll() not in (0, None))
        assert opener.wait(timeout=5) == 0
    finally:
        if opener.poll() is None:
            opener.terminate()
            opener.wait()
    doc = next(w for w in app.get_windows() if w.path == file)
    assert win.buffer.get_modified() and doc.buffer.get_text(*doc.buffer.get_bounds(), True) == 'café\n'
    if os.environ.get('EDITOR_CHECK_SCREENSHOT'):
        wait(lambda: doc.view.get_mapped() and doc.view.get_allocated_width() == 776)
        subprocess.run(['grim', os.environ['EDITOR_CHECK_SCREENSHOT']], check=True)
    doc.buffer.insert_at_cursor('π ')
    doc.save()
    assert file.read_bytes() == codecs.BOM_UTF8 + 'π café\r\n'.encode()
    doc.buffer.insert_at_cursor('edit')
    file.write_bytes(b'external change')
    doc.save()
    assert doc.buffer.get_modified() and file.read_bytes() == b'external change'
    assert doc.stack.get_visible_child_name() == 'panel'
    doc.document()
    doc.choose(True)
    panel = doc.stack.get_child_by_name('panel')
    wait(lambda: panel.get_allocated_height() > 1)
    inside(doc, panel)
    entry = next(w for w in panel.get_children() if isinstance(w, Gtk.Entry))
    assert entry.get_allocated_height() >= 56
    save_button = panel.get_children()[-1].get_children()[0]
    assert save_button.get_label() == 'Save'
    entry.set_text('')
    assert not save_button.get_sensitive()
    entry.set_text('copy.txt')
    nested = root / 'Saved notes'
    nested.mkdir()
    destination = panel.get_children()[-2]
    destination.clicked()
    picker = doc.stack.get_child_by_name('panel')
    wait(lambda: picker.get_allocated_height() > 1)
    inside(doc, picker)
    scroll = next(w for w in picker.get_children() if isinstance(w, Gtk.ScrolledWindow))
    rows = scroll.get_child().get_child()
    next(row for row in rows.get_children() if row.get_accessible().get_name() == nested.name).clicked()
    picker = doc.stack.get_child_by_name('panel')
    picker.get_children()[-1].get_children()[0].clicked()
    panel = doc.stack.get_child_by_name('panel')
    copy = nested / 'copy.txt'
    assert next(w for w in panel.get_children() if isinstance(w, Gtk.Entry)).get_text() == copy.name
    panel.get_children()[-1].get_children()[0].clicked()
    assert copy.exists() and not doc.buffer.get_modified()
    doc.buffer.insert_at_cursor('more')
    doc.save_as(file, None)
    assert doc.stack.get_visible_child_name() == 'panel' and file.read_bytes() == b'external change'
    doc.document()
    binary = root / 'binary'
    binary.write_bytes(b'\x00bad')
    doc.load(binary)
    assert doc.path == copy and doc.buffer.get_modified()
    for window in app.get_windows():
        window.destroy()


def open_fixture(file):
    files = RoundFiles(str(file.parent))
    files.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    assert files.register(None)
    files.activate()
    wait(lambda: files.location and files.row_widgets)
    result = []
    def finished(source, response, data):
        result.append(Gio.AppInfo.launch_default_for_uri_finish(response))
    files.opened = finished
    target = Gio.File.new_for_path(str(file))
    files.open_item(target.query_info('standard::*', Gio.FileQueryInfoFlags.NONE, None))
    wait(lambda: result)
    assert result == [True]
    files.window.destroy()


if __name__ == '__main__':
    if sys.argv[1:2] == ['--open-fixture']:
        open_fixture(Path(sys.argv[2]))
        sys.exit(0)
    GLib.set_prgname('aroundos-editor')
    with tempfile.TemporaryDirectory(prefix='round-editor-check-') as directory:
        check(Path(directory))
    print('PASS: Apps launch, Files open, full display and circular controls, draft protection, '
          'UTF-8/BOM/CRLF save, external-change protection, Save As, overwrite guard, binary rejection.')
