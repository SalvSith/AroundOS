#!/usr/bin/env python3
"""Exercise the panel module's task filter with real GTK show/title events.

Run in the Pi desktop session with GTK_MODULES set to round-surfaces.so.
"""
import ctypes
import os
import sys
import tempfile
import time
from pathlib import Path

# Exercise atomic watcher updates without writing the real panel's map.
session_runtime = Path(os.environ['XDG_RUNTIME_DIR'])
runtime = tempfile.TemporaryDirectory()
os.environ['WAYLAND_DISPLAY'] = str(session_runtime / os.environ.get('WAYLAND_DISPLAY', 'wayland-0'))
os.environ['XDG_RUNTIME_DIR'] = runtime.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
from round_windows import TASK_ICONS, task_icon_map
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf
from round_motion import (_bind, _gtk, _cairo, _ptr, _double, _surface_create,
                          _surface_destroy, _context_create, _context_destroy, _paint)

draw_widget = _bind(_gtk, 'gtk_widget_draw', [_ptr, _ptr])
set_source = _bind(ctypes.CDLL('libgdk-3.so.0'), 'gdk_cairo_set_source_pixbuf',
                   [_ptr, _ptr, _double, _double])
surface_data = _bind(_cairo, 'cairo_image_surface_get_data', [_ptr], _ptr)
surface_flush = _bind(_cairo, 'cairo_surface_flush', [_ptr])


def settle():
    while Gtk.events_pending():
        Gtk.main_iteration()

def pixels(image, pixbuf=None):
    w, h = image.get_allocated_width(), image.get_allocated_height()
    surface = _surface_create(0, w, h)  # CAIRO_FORMAT_ARGB32
    ctx = _context_create(surface)
    try:
        if pixbuf is None:
            draw_widget(hash(image), ctx)
        else:
            set_source(ctx, hash(pixbuf), (w - pixbuf.get_width()) // 2, (h - pixbuf.get_height()) // 2)
            _paint(ctx)
        surface_flush(surface)
        return ctypes.string_at(surface_data(surface), w * h * 4)
    finally:
        _context_destroy(ctx)
        _surface_destroy(surface)

def publish(windows):
    tmp = TASK_ICONS.with_suffix('.tmp')
    tmp.write_text(task_icon_map(windows))
    tmp.replace(TASK_ICONS)

def check_art(widget, name):
    if name:
        source = Path(sys.path[0]) / 'dock-icons/cutouts' / (name + '.png')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source)).scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)
    else:
        pixbuf = stock
    deadline = time.monotonic() + 2
    while True:
        settle()
        if widget.get_allocated_width() >= 32 and pixels(widget) == pixels(widget, pixbuf):
            break
        assert time.monotonic() < deadline, f'wrong rendered pixels for {name or "native icon"}'
        time.sleep(.02)

cases = {
    'aroundos-browser': 'browser', 'aroundos-round-files': 'files', 'aroundos-terminal': 'terminal',
    'aroundos-settings': 'settings', 'aroundos-photos': 'photos', 'aroundos-editor': 'editor',
    'lxtask': 'task-manager', 'chrome-127.0.0.1__aroundos-dial_-Default': 'dial',
    'vlc': 'vlc', 'aroundos-navcon': 'navcon', 'pishutdown': 'shutdown',
}
windows = [{'app_id': app, 'title': ('Task Manager · AroundOS' if app == 'lxtask' else
            f'File / {index} [100%] = 窗口'), 'states': [1]} for index, app in enumerate(cases)]
publish(windows)
stock = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 32, 32)
stock.fill(0xe04080ff)

window = Gtk.Window()
window.set_name('PanelToplevel')
root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
window.add(root)
tasks = Gtk.Box()
tasks.set_name('window-list')
root.add(tasks)
launchpad = Gtk.ToggleButton()
files = Gtk.ToggleButton()
art = Gtk.Image.new_from_pixbuf(stock)
files.add(art)
tasks.add(launchpad)
tasks.add(files)
outside = Gtk.ToggleButton()
outside.set_tooltip_text('Apps · AroundOS')
root.add(outside)
launchers = Gtk.Box()
launchers.set_name('launchers')
root.add(launchers)
pin = Gtk.Button()
pin.set_name('aroundos-launchpad.desktop')
rocket = Gtk.Image.new_from_pixbuf(stock)
pin.add(rocket)
shortcut = Gtk.Button()
shortcut.set_name('aroundos-files.desktop')
launchers.add(pin)
launchers.add(shortcut)
window.show_all()
settle()

# The real plugin sets its tooltip only after showing the new button.
launchpad.set_tooltip_text('Apps · AroundOS')
files.set_tooltip_text('Files · AroundOS')
settle()
assert not launchpad.get_visible(), 'duplicate task must be hidden'
assert files.get_visible(), 'other app tasks must remain visible'
assert outside.get_visible(), 'filter must stay scoped to the window list'
assert pin.get_visible(), 'Launchpad must stay pinned'
assert not shortcut.get_visible(), 'other apps must not be pinned on top'
check_art(rocket, 'launchpad')
for handle, icon in zip(windows, cases.values()):
    files.set_tooltip_text(handle['title'])
    check_art(art, icon)
files.set_tooltip_text('File Manager')
check_art(art, None)
# An unknown app with the same title must keep its native art. Reading
# the new mapping also exercises a title change without resizing a button.
title = windows[0]['title']
files.set_tooltip_text(title)
publish(windows + [{'app_id':'chromium', 'title':title}])
check_art(art, None)
publish(windows)
check_art(art, 'browser')
art.destroy()
art = Gtk.Image.new_from_pixbuf(stock)
files.add(art)
art.show()
check_art(art, 'browser')
files.set_tooltip_text('Task Manager')
publish([{'title':'Task Manager', 'app_id':'lxtask'}])
check_art(art, None)
window.show_all()
launchpad.show()
settle()
assert not launchpad.get_visible(), 'later panel refresh must not revive duplicate'
assert not shortcut.get_visible(), 'panel refresh must not revive other pins'
launchpad.set_tooltip_text('Another application')
settle()
assert launchpad.get_visible(), 'a changed title must restore an ordinary task'
launchpad.set_tooltip_text('Apps · AroundOS')
settle()
assert not launchpad.get_visible(), 'changed title must be filtered again'
files.destroy()
settle()
assert files not in tasks.get_children(), 'closed tasks must be removed normally'
window.destroy()
settle()
print('PASS: pinned rocket, 11 app cutouts, utility and collision fallback, refresh, retitling and close')
