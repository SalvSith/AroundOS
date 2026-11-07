#!/usr/bin/env python3
"""Live layer-shell geometry, magnification and artwork checks using test-only buttons.

Run on the Pi with GTK_MODULES pointing to the surface module, an empty temporary
XDG_RUNTIME_DIR, and an absolute WAYLAND_DISPLAY pointing to the real socket.
Use the test-only glass-launcher-probe.so with LD_PRELOAD and set
GLASS_CHECK_EVENTS to a temporary path to verify launch/save without side effects.
Without the probe, tap-launch checks are skipped. Optional argument: screenshot output directory.
Run the same check with AROUNDOS_REDUCE_MOTION=1 or an isolated XDG_CONFIG_HOME
containing aroundos-round/dock-motion-off to verify the original-art-only path.
Copy the user's gtk-3.0 and dconf directories into that temporary config so the
fixture uses the panel's actual press styling and GTK animation preference.
"""
import configparser
import ctypes
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
import time
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib

layer = ctypes.CDLL('libgtk-layer-shell.so.0', mode=ctypes.RTLD_GLOBAL)
for name, args in [('gtk_layer_init_for_window', [ctypes.c_void_p]),
                   ('gtk_layer_set_layer', [ctypes.c_void_p, ctypes.c_int]),
                   ('gtk_layer_set_anchor', [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
                   ('gtk_layer_set_namespace', [ctypes.c_void_p, ctypes.c_char_p])]:
    getattr(layer, name).argtypes = args
    getattr(layer, name).restype = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
if not (Path(sys.path[0]) / 'round_windows.py').exists():
    sys.path.insert(0, str(Path.home() / 'AroundOS/src/round-desktop'))
from round_windows import Windows, uint, string
from round_motion import (_bind, _gtk, _cairo, _ptr, _surface_create, _surface_destroy,
                          _context_create, _context_destroy)

class Pointer:
    """Drive a compositor pointer over the test-only dock buttons."""
    def __init__(self):
        self.client = Windows()
        c = self.client
        name, version = c.globals['zwlr_virtual_pointer_manager_v1']
        self.manager = c.next_id + 1
        self.pointer = self.manager + 1
        c.next_id = self.pointer
        c.send(2, 0, uint(name) + string('zwlr_virtual_pointer_manager_v1') + uint(min(version, 2), self.manager))
        c.send(self.manager, 0, uint(0, self.pointer)); c.roundtrip()
        self.target = None
        self.closed = False
        GLib.timeout_add(80, self.maintain)

    def maintain(self):
        if self.closed: return False
        if self.target: self.send_position(*self.target)
        return True

    def move(self, x, y):
        self.target = (x, y)
        self.send_position(x, y)

    def send_position(self, x, y):
        self.client.send(self.pointer, 1, uint(int(time.monotonic()*1000) & 0xffffffff, int(x), int(y), 1080, 1080))
        self.client.send(self.pointer, 4); self.client.roundtrip()

    def left_button(self, pressed):
        self.client.send(self.pointer, 2, uint(int(time.monotonic()*1000) & 0xffffffff, 0x110, int(pressed)))
        self.client.send(self.pointer, 4); self.client.roundtrip()

    def close(self):
        self.closed = True
        self.move(540, 540)
        self.client.send(self.pointer, 8); self.client.send(self.manager, 1)
        self.client.close()

pointer = Pointer()

events_path = Path(os.environ['GLASS_CHECK_EVENTS']) if os.environ.get('GLASS_CHECK_EVENTS') else None
if events_path: events_path.write_text('')
def actions():
    return events_path.read_text().splitlines() if events_path else []

checks = []
windows = []
failed = False
output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if output: output.mkdir(parents=True, exist_ok=True)


def check(name, value):
    if not value: raise AssertionError(name)
    checks.append(name)


LAUNCHERS = (
    ('aroundos-launchpad', 'launchpad', 'start-here', 'Apps'),
    ('x-www-browser', 'browser', 'web-browser', 'Web Browser'),
    ('aroundos-terminal', 'terminal', 'utilities-terminal', 'Terminal'),
    ('aroundos-files', 'files', 'folder', 'Files'),
    ('aroundos-editor', 'editor', 'text-x-generic', 'Text Editor'),
    ('aroundos-settings', 'settings', 'preferences-system', 'System Settings'),
    ('aroundos-sleep', 'sleep', 'weather-clear-night-symbolic', 'Sleep'),
)
DOCK_ART = tuple(art for _, art, _, _ in LAUNCHERS)


def button(ident, icon, title):
    item = Gtk.Button()
    item.set_name(ident + '.desktop')
    item.set_tooltip_text(title)
    pixbuf = Gtk.IconTheme.get_default().load_icon(icon, 52, Gtk.IconLookupFlags.FORCE_SIZE)
    item.add(Gtk.Image.new_from_pixbuf(pixbuf))
    return item


def bar(dock):
    window = Gtk.Window()
    window.set_name('DockToplevel' if dock else 'PanelToplevel')
    pointer = hash(window)
    layer.gtk_layer_init_for_window(pointer)
    layer.gtk_layer_set_namespace(pointer, b'aroundos-glass-check')
    layer.gtk_layer_set_layer(pointer, 3)
    layer.gtk_layer_set_anchor(pointer, 3 if dock else 2, 1)
    box = Gtk.Box()
    window.add(box)
    launchers = Gtk.Box()
    launchers.set_name('launchers')
    box.add(launchers)
    items = [button(ident, icon, title) for ident, _, icon, title in LAUNCHERS]
    for item in items: launchers.add(item)
    if not dock:
        tasks = Gtk.Box(); tasks.set_name('window-list'); box.add(tasks)
        task = Gtk.ToggleButton(); task.add(Gtk.Image.new_from_icon_name('folder', Gtk.IconSize.DIALOG))
        task.get_child().set_pixel_size(32)
        tasks.add(task); items.append(task)
        task.set_tooltip_text('Files · AroundOS')
        # Connect before the module installs its hover draw handler. Model a
        # style/layout update arriving during the first hovered draw pass.
        task.pending_hover_resize = False
        def pending_resize(*_):
            if task.pending_hover_resize:
                task.get_child().queue_resize()
            return 0
        task.resize_callback = ctypes.CFUNCTYPE(ctypes.c_int, _ptr, _ptr, _ptr)(pending_resize)
        connect_draw(hash(task), b'draw', task.resize_callback, None, None, 0)
    window.show_all()
    windows.append(window)
    return window, items


draw_widget = _bind(_gtk, 'gtk_widget_draw', [_ptr, _ptr])
connect_draw = _bind(ctypes.CDLL('libgobject-2.0.so.0'), 'g_signal_connect_data',
                     [_ptr, ctypes.c_char_p, _ptr, _ptr, _ptr, ctypes.c_int], ctypes.c_ulong)
surface_data = _bind(_cairo, 'cairo_image_surface_get_data', [_ptr], _ptr)
surface_flush = _bind(_cairo, 'cairo_surface_flush', [_ptr])


def ink_bounds(button):
    w, h = button.get_allocated_width(), button.get_allocated_height()
    surface = _surface_create(0, w, h)
    ctx = _context_create(surface)
    try:
        draw_widget(hash(button), ctx)
        surface_flush(surface)
        alpha = ctypes.string_at(surface_data(surface), w * h * 4)[3::4]
        ink = [i for i, a in enumerate(alpha) if a >= 128]
        return min(i % w for i in ink), max(i % w for i in ink), min(ink) // w, max(ink) // w
    finally:
        _context_destroy(ctx)
        _surface_destroy(surface)


def panel_hover():
    clock = Gtk.Button(label='12:00')
    clock.set_name('clock')
    top.get_child().add(clock)
    clock.show_all()
    wifi = Gtk.Button.new_from_icon_name('network-wireless-symbolic', Gtk.IconSize.LARGE_TOOLBAR)
    wifi.set_name('netman')
    top.get_child().add(wifi)
    wifi.show_all()
    yield 500
    buttons = (top_items[0], top_items[-1], clock, wifi)
    boxes = [position(b, top) for b in buttons]
    rest = [ink_bounds(b) for b in buttons]
    for i, (button, label) in enumerate(zip(buttons, ('Apps', 'running task', 'clock', 'Wi-Fi'))):
        x, y, w, h = boxes[i]
        pointer.move((1080 - top.get_allocated_width()) / 2 + x + w / 2, 24 + y + h / 2)
        samples = set()
        for _ in range(16):
            yield 45
            samples.add(ink_bounds(button))
        hovered = ink_bounds(button)
        if motion_off:
            check(f'{label} stays still', samples == {rest[i]})
        else:
            a, b, c, d = rest[i]
            left, right, upper, lower = hovered
            check(f'{label} eases through intermediate sizes', len(samples - {rest[i], hovered}) > 0)
            check(f'{label} grows subtly', 1 <= (right - left) - (b - a) <= (b - a) * .19 + 1)
            check(f'{label} moves slightly toward screen center', 2 <= (upper + lower - c - d) / 2 <= 5.5)
        check(f'{label} hover keeps adjacent artwork still',
              all(ink_bounds(other) == rest[j] for j, other in enumerate(buttons) if j != i))
        check(f'{label} hover keeps all input targets fixed', [position(b, top) for b in buttons] == boxes)
        pointer.move(540, 540)
        yield 720
        check(f'{label} returns to rest on leave', ink_bounds(button) == rest[i])
    # Check compositor output, not gtk_widget_draw(): offscreen redraws alone
    # miss the blank on-screen frame when a hover has queued a fresh layout.
    task = top_items[-1]
    marker = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 32, 32)
    marker.fill(0xf007c3ff)
    task.get_child().set_from_pixbuf(marker)
    yield 200
    x, y, w, h = position(task, top)
    pointer.move((1080 - top.get_allocated_width()) / 2 + x + w / 2, 24 + y + h / 2)
    task.pending_hover_resize = True
    try:
        for frame in range(4):
            yield 45
            loader = GdkPixbuf.PixbufLoader.new_with_type('png')
            loader.write(subprocess.check_output(['grim', '-']))
            loader.close()
            shot = loader.get_pixbuf()
            # Keep screenshots in memory on the Pi; report only test results.
            data, channels = shot.get_pixels(), shot.get_n_channels()
            count = sum(data[i] > 220 and data[i + 1] < 30 and 175 < data[i + 2] < 215
                        for i in range(0, len(data) - channels + 1, channels))
            check(f'pending hover layout keeps icon visible in screen frame {frame}', count >= 1024)
    finally:
        task.pending_hover_resize = False
        task.get_child().set_from_icon_name('folder', Gtk.IconSize.DIALOG)
        task.get_child().set_pixel_size(32)
        pointer.move(540, 540)
    yield 720
    wifi.destroy()
    clock.destroy()
    yield 250


class TouchLayout(ctypes.Structure):
    _fields_ = [('type',ctypes.c_int),('window',ctypes.c_void_p),
                ('send_event',ctypes.c_byte),('time',ctypes.c_uint),
                ('x',ctypes.c_double),('y',ctypes.c_double),
                ('axes',ctypes.c_void_p),('state',ctypes.c_uint),
                ('sequence',ctypes.c_void_p)]

sequence = ctypes.c_int(1)
display = Gdk.Display.get_default()
touch_device = next(d for d in display.get_device_manager().list_devices(Gdk.DeviceType.SLAVE)
                    if d.get_source() == Gdk.InputSource.TOUCHSCREEN)

def touch(item, window, kind, x, y):
    event = Gdk.Event.new(getattr(Gdk.EventType, 'TOUCH_' + kind))
    origin = window.get_window().get_origin()
    # Target the actual button's event window; exercise GTK capture and the
    # competing native bubble gesture, not direct signal callbacks.
    target = item.get_event_window()
    target_origin = target.get_origin()
    event.touch.window = target
    event.touch.x_root = origin[-2] + x
    event.touch.y_root = origin[-1] + y
    event.touch.x = event.touch.x_root-target_origin[-2]
    event.touch.y = event.touch.y_root-target_origin[-1]
    event.touch.send_event = True
    event.touch.emulating_pointer = True
    event.touch.time = int(time.monotonic()*1000) & 0xffffffff
    event.set_device(display.get_default_seat().get_pointer())
    event.set_source_device(touch_device)
    TouchLayout.from_address(hash(event)).sequence = ctypes.addressof(sequence)
    Gtk.main_do_event(event)


def position(item, window):
    a = item.get_allocation()
    x, y = item.translate_coordinates(window, 0, 0)
    return x, y, a.width, a.height


def bounds(window, items, dock, name):
    width, height = window.get_size()
    for item in items:
        if not item.get_visible(): continue
        x, y, w, h = position(item, window)
        sy = 1080 - 24 - height if dock else 24
        sx = (1080 - width) / 2
        radius = max(math.hypot(sx + px - 540, sy + py - 540)
                     for px in (x, x+w) for py in (y, y+h))
        check(name + ' inside circle ' + item.get_name(), radius < 532)
        check(name + ' unclipped ' + item.get_name(), x >= 0 and y >= 0 and x+w <= width and y+h <= height)


def screenshot(name):
    if output: subprocess.run(['grim', str(output / (name + '.png'))], check=True)


motion_off = (os.environ.get('AROUNDOS_REDUCE_MOTION', '').lower() in ('1', 'true', 'yes')
              or (Path(GLib.get_user_config_dir()) / 'aroundos-round/dock-motion-off').exists())


@lru_cache(maxsize=len(LAUNCHERS))
def original_art(name):
    path = Path(sys.path[0]) / 'dock-icons' / 'cutouts' / (name + '.png')
    return GdkPixbuf.Pixbuf.new_from_file(str(path))


@lru_cache(maxsize=256)
def original_pixels(name, size):
    return original_art(name).scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR).get_pixels()


def dock_frame(item):
    art = item.get_child().get_pixbuf()
    if art is None or art.get_width() != art.get_height() or not 56 <= art.get_width() <= 90:
        raise AssertionError(f'{item.get_name()} invalid dock image dimensions')
    width = art.get_width()
    stride = art.get_rowstride()
    pixels = art.get_pixels()
    if stride != width * 4:  # A subpixbuf into an atlas may have extra bytes between rows.
        pixels = b''.join(pixels[row*stride:row*stride + width*4] for row in range(width))
    return width, pixels


def dock_is_static(item, name):
    width, pixels = dock_frame(item)
    return pixels == original_pixels(name, width)


def check_dock_art(item, name, size):
    width, pixels = dock_frame(item)
    check(f'{name} dock artwork at {size}px', width == size and pixels == original_pixels(name, size))


def dock_bounds(name):
    bounds(dock, dock_items, True, name)
    boxes = [position(item, dock) for item in dock_items]
    check(f'{name} dock targets do not overlap',
          all(x + w <= next_box[0] for (x, _, w, _), next_box in zip(boxes, boxes[1:])))


def hover_motion(item, name):
    pointer.move(540, 540)
    yield 700
    x, y, w, h = position(item, dock)
    sw, sh = dock.get_size()
    pointer.move((1080 - sw)/2 + x + w/2, 1080 - 24 - sh + y + h/2)
    by_size = {}
    moving_neighbors = set()
    for _ in range(18):
        yield 80
        width, pixels = dock_frame(item)
        if pixels != original_pixels(name, width):
            by_size.setdefault(width, set()).add(pixels)
        for neighbor, neighbor_name in zip(dock_items, DOCK_ART):
            if item != neighbor and not dock_is_static(neighbor, neighbor_name):
                moving_neighbors.add(neighbor_name)
    check(f'{name} hover still magnifies', position(item, dock)[2] >= w + 20)
    if name in ('launchpad', 'editor', 'sleep'):
        dock_bounds(f'{name} expanded')
    check(f'{name} hover leaves neighbors static (unexpected frames: {sorted(moving_neighbors)})', not moving_neighbors)
    if motion_off:
        check(f'{name} preference preserves original art throughout hover', not by_size)
    else:
        # Multiple changed images at one identical width rule out magnification
        # and a single replacement hover image as explanations for the change.
        check(f'{name} hover plays multiple distinct frames', any(len(frames) >= 2 for frames in by_size.values()))
        if name == 'editor':
            width, observed = max(by_size.items(), key=lambda pair: len(pair[1]))
            strip = GdkPixbuf.Pixbuf.new_from_file(str(Path(sys.path[0]) / 'dock-icons/motion/editor.png'))
            side = strip.get_height()
            authored = set()
            for x in range(0, strip.get_width(), side):
                tile = strip.new_subpixbuf(x, 0, side, side)
                authored.add(tile.scale_simple(width, width, GdkPixbuf.InterpType.BILINEAR).get_pixels())
            check('Editor hover displays multiple authored Editor frames at the same size', len(observed & authored) >= 2)
    yield 520
    settled = []
    for _ in range(8):
        settled.append(dock_is_static(item, name))
        yield 100
    check(f'{name} stays at the original cutout while still hovered', all(settled))


def steps():
    pointer.move(540, 540)
    yield 500
    # Touch coordinates outside the surface establish a pointer-independent baseline.
    yield 800
    yield from panel_hover()
    if os.environ.get('AROUNDOS_CHECK_PANEL_ONLY') == '1':
        return
    bounds(top, top_items, False, 'top')
    dock_bounds('rest')
    check('only Launchpad pinned on top', top_items[0].get_visible() and all(not i.get_visible() for i in top_items[1:-1]))
    editor = dock_items[DOCK_ART.index('editor')]
    editor_entry = Gio.DesktopAppInfo.new(editor.get_name())
    check('Editor dock button resolves to the installed round editor',
          editor_entry is not None and editor_entry.get_id() == 'aroundos-editor.desktop'
          and 'round_editor.py' in editor_entry.get_commandline())
    check('Editor stays off the permanent top bar', not top_items[DOCK_ART.index('editor')].get_visible())
    panel = configparser.ConfigParser()
    panel.read(Path(sys.path[0]) / 'wf-panel-pi.ini')
    for section in ('panel', 'dock'):
        ids = panel.get(section, 'launchers').split()
        check(f'{section} configuration puts one Editor immediately after Files',
              ids.count('aroundos-editor') == 1 and ('aroundos-files', 'aroundos-editor') in zip(ids, ids[1:]))
    check('running app shown on top', top_items[-1].get_visible())
    check('all dock shortcuts retained', all(i.get_visible() for i in dock_items))
    for item, name in zip(dock_items, DOCK_ART):
        check_dock_art(item, name, 56)
    # The top bar paints over the native image. check-round-task-icons.py
    # compares the rendered launcher and task pixels against their cutouts.
    left = position(dock_items[0], dock); right = position(dock_items[-1], dock)
    middle = position(dock_items[DOCK_ART.index('files')], dock)
    check('dock follows lower circular arc', middle[1] > max(left[1], right[1]) + 12)
    terminal = dock_items[DOCK_ART.index('terminal')]
    baseline = position(terminal, dock)
    screenshot('glass-rest')
    for item, name in zip(dock_items, DOCK_ART):
        yield from hover_motion(item, name)
        if name == 'terminal':
            # No mouse departure: a fresh touch on the same settled icon gets
            # its own performance. Cancel without releasing a launch action.
            x, y, w, h = position(item, dock)
            cx, cy = x + w/2, y + h/2
            touch(item, dock, 'BEGIN', cx, cy)
            samples = []
            for _ in range(4):
                yield 60
                samples.append(not dock_is_static(item, name))
            touch(item, dock, 'CANCEL', cx, cy)
            check('new finger contact on a settled hovered icon follows motion preference', any(samples) == (not motion_off))
            yield 1600
    pointer.move(540, 540)
    yield 700
    sw, sh = dock.get_size()
    pointer.move((1080-sw)/2 + baseline[0]+baseline[2]/2, 1080-24-sh + baseline[1]+baseline[3]/2)
    reentry_played = False
    for _ in range(9):
        yield 100
        reentry_played |= not dock_is_static(terminal, 'terminal')
    check('terminal hover responds to reentry or static preference', reentry_played == (not motion_off))
    check('real compositor mouse hover enlarges icon', position(terminal, dock)[2] >= baseline[2]+24)
    screenshot('mouse-hover')
    item = terminal
    x, y, w, h = position(item, dock)
    pointer.move((1080-sw)/2+x+w/2, 1080-24-sh+y+h/2)
    pointer.left_button(True)
    yield 100
    mouse_pressed = item.get_state_flags() & Gtk.StateFlags.ACTIVE
    mouse_fill = item.get_style_context().get_background_color(item.get_state_flags()).alpha
    pointer.left_button(False)
    yield 100
    check('mouse down shows dock press fill', mouse_pressed and mouse_fill > 0.15)
    released = item.get_state_flags()
    release_color = item.get_style_context().get_background_color(released)
    check(f'mouse release clears press fill (state={released}, color={release_color.to_string()}, '
          f'classes={item.get_style_context().list_classes()}, theme={Gtk.Settings.get_default().props.gtk_theme_name})',
          release_color.alpha < 0.01)
    pointer.move(540, 540)
    yield 950
    check('real compositor mouse departure collapses icon', abs(position(terminal, dock)[2]-baseline[2]) <= 1)
    pointer.move((1080-sw)/2 + baseline[0]+baseline[2]/2, 1080-24-sh + baseline[1]+baseline[3]/2)
    yield 950
    check('real mouse reentry restores animation', position(terminal, dock)[2] >= baseline[2]+24)
    pointer.move(540, 540)
    yield 700
    item = terminal
    parent = item.get_parent()
    original = parent.get_children()
    x,y,w,h = position(item,dock)
    cx,cy = x+w/2,y+h/2
    native = Gtk.GestureDrag.new(item)
    native_events = []
    native.connect('drag-update', lambda *a: native_events.append(True))
    touch(item,dock,'BEGIN',cx,cy)
    touch_played = False
    for _ in range(4):
        yield 50
        touch_played |= not dock_is_static(item, 'terminal')
    check('finger contact plays terminal artwork or respects static preference', touch_played == (not motion_off))
    style = item.get_style_context()
    check('touch down shows dock press fill', style.has_class('dock-pressed') and
          style.get_background_color(item.get_state_flags()).alpha > 0.15)
    ex, ey, ew, eh = position(editor, dock)
    touch(item,dock,'UPDATE',ex+ew/2,ey+eh/2)
    yield 700
    check('swipe clears press feedback', not style.has_class('dock-pressed'))
    check('swipe does not rearrange',parent.get_children()==original)
    check('finger slide from Terminal magnifies Editor',position(editor,dock)[2] >= w+20)
    touch(item,dock,'UPDATE',cx,cy)
    yield 700
    check('animation follows finger back',position(item,dock)[2] >= w+24)
    check('swipe cannot turn into a delayed reorder',parent.get_children()==original)
    screenshot('touch-slide')
    touch(item,dock,'END',cx,cy)
    yield 950
    check('finger release collapses animation',position(item,dock)[2]==w)
    check('native drag handler never receives swipe',not native_events)
    if events_path: check('swipe neither launches nor saves',not actions())
    touch(item,dock,'BEGIN',cx,cy)
    yield 650
    held_frames = []
    for _ in range(6):
        held_frames.append(all(dock_is_static(i, n) for i, n in zip(dock_items, DOCK_ART)))
        yield 90
    check('rearrange hold returns all seven icons to their original artwork', all(held_frames))
    check('hold replaces press feedback', not style.has_class('dock-pressed'))
    check('stationary hold lifts selected icon',position(item,dock)[1] <= y-9)
    check('held icon keeps stable width',position(item,dock)[2]==w)
    ex, ey, ew, eh = position(editor, dock)
    drop_x = ex + ew/2 + 13
    touch(item,dock,'UPDATE',drop_x,cy)
    yield 200
    check('hold then drag moves Terminal past Editor',
          parent.get_children().index(item) > parent.get_children().index(editor))
    check('rearrange drag keeps original artwork', all(dock_is_static(i, n) for i, n in zip(dock_items, DOCK_ART)))
    screenshot('touch-rearrange')
    touch(item,dock,'CANCEL',drop_x,cy)
    yield 350
    check('cancel restores original order',parent.get_children()==original)
    check('cancel clears lifted state',position(item,dock)[1]==y)
    if events_path: check('cancel neither launches nor saves',not actions())
    touch(item,dock,'BEGIN',cx,cy)
    yield 1200
    touch(item,dock,'UPDATE',drop_x,cy)
    yield 200
    touch(item,dock,'END',drop_x,cy)
    yield 350
    check('release retains deliberate reorder',parent.get_children().index(item)>parent.get_children().index(editor))
    check('release clears touch size',position(item,dock)[2]==w)
    check('native drag remains suppressed',not native_events)
    if events_path:
        expected = 'save ' + ''.join(i.get_name().removesuffix('.desktop')+' ' for i in parent.get_children())
        check('release saves exact launcher order once',actions()==[expected])
        x,y,w,h = position(item,dock)
        touch(item,dock,'BEGIN',x+w/2,y+h/2)
        yield 80
        check('quick tap waits for release', actions() == [expected])
        touch(item,dock,'END',x+w/2,y+h/2)
        check('tap launches on release within the artwork timeline', actions() == [expected, 'launch'])
        yield 150
        check('tap release clears press feedback', not style.has_class('dock-pressed'))
        check('quick tap launches exactly once',actions()==[expected,'launch'])
        touch(item,dock,'BEGIN',x+w/2,y+h/2)
        yield 700
        touch(item,dock,'END',x+w/2,y+h/2)
        yield 150
        check('hold without movement never launches',actions()==[expected,'launch'])
        ex, ey, ew, eh = position(editor, dock)
        touch(editor,dock,'BEGIN',ex+ew/2,ey+eh/2)
        yield 80
        check('Editor tap waits for release', actions()==[expected,'launch'])
        touch(editor,dock,'END',ex+ew/2,ey+eh/2)
        check('Editor tap launches exactly once on release', actions()==[expected,'launch','launch'])
        yield 350
        check('Editor tap releases its press state without a second launch',
              not editor.get_style_context().has_class('dock-pressed') and actions()==[expected,'launch','launch'])
    bounds(dock,dock_items,True,'touch reordered')
    expanded = top.get_child().get_allocated_width()
    top_items[-1].destroy()
    yield 250
    check('closing app removes task', top_items[-1].get_parent() is None)
    check('top bar shrinks when apps close', top.get_child().get_allocated_width() < expanded - 20)
    check('empty top bar remains compact', top.get_child().get_allocated_width() < 200)


top, top_items = bar(False)
dock, dock_items = bar(True)
iterator = steps()

def advance():
    global failed
    try:
        delay = next(iterator)
        GLib.timeout_add(delay, advance)
        return False
    except StopIteration:
        pass
    except Exception:
        traceback.print_exc(); failed = True
    pointer.close()
    for window in windows: window.destroy()
    Gtk.main_quit()
    return False

GLib.idle_add(advance)
Gtk.main()
print(json.dumps({'passed': not failed, 'checks': len(checks), 'last': checks[-1] if checks else None}))
raise SystemExit(1 if failed else 0)
