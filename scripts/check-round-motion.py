#!/usr/bin/env python3
"""Live Launchpad reveal, lifecycle, render and frame-time checks on the Pi."""
import json
import os
from pathlib import Path
import statistics
import sys
import time
import traceback
import ctypes

import cairo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
import round_shell
from round_shell import Shell, Gtk, Gdk, Gio, GLib
from round_motion import LaunchpadReveal, reveal_pose
from round_motion import _bind, _cairo, _gtk, _ptr, _double
from round_windows import activate

checks = []
frames = []
draw_times = []
failed = False


def check(name, value):
    if not value:
        raise AssertionError(name)
    checks.append(name)


class MeasuredReveal(LaunchpadReveal):
    def advance(self, widget, clock):
        frames.append(clock.get_frame_time())
        return super().advance(widget, clock)

    def draw_native(self, widget, cr, data):
        start = time.perf_counter()
        animated = self.elapsed < self.DURATION
        result = super().draw_native(widget, cr, data)
        if animated:
            draw_times.append((time.perf_counter() - start) * 1000)
        return result


round_shell.LaunchpadReveal = MeasuredReveal
GLib.set_prgname('aroundos-motion-check')
app = Shell('launchpad')
app.set_application_id('org.aroundos.MotionCheck')
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)


def snapshot(elapsed):
    app.fixed.elapsed = elapsed
    surface = _bind(_cairo, 'cairo_image_surface_create', [ctypes.c_int]*3, _ptr)(0, 1080, 1080)
    cr = _bind(_cairo, 'cairo_create', [_ptr], _ptr)(surface)
    _bind(_cairo, 'cairo_set_source_rgb', [_ptr, _double, _double, _double])(cr, 16/255, 16/255, 18/255)
    _bind(_cairo, 'cairo_paint', [_ptr])(cr)
    _bind(_gtk, 'gtk_widget_draw', [_ptr, _ptr])(hash(app.window), cr)
    path = f'/tmp/aroundos-motion-frame-{elapsed}.png'
    _bind(_cairo, 'cairo_surface_write_to_png', [_ptr, ctypes.c_char_p], ctypes.c_int)(surface, path.encode())
    _bind(_cairo, 'cairo_destroy', [_ptr])(cr)
    _bind(_cairo, 'cairo_surface_destroy', [_ptr])(surface)
    return cairo.ImageSurface.create_from_png(path)


def geometry():
    return [(b.x, b.y, b.width, b.height) for b in (w.get_allocation() for w in app.dynamic)]


def steps():
    yield 800
    reveal = app.fixed
    check('cold open animates on frame clock', len(frames) >= 3)
    check('cold open settles', reveal.tick_id is None and reveal.elapsed == reveal.DURATION)
    check('cold open draws animation', len(draw_times) >= 3)
    reveal.start()
    yield 40
    original_buttons=list(app.dynamic)
    app.reload_apps()
    source=app.apps_reload_source
    app.reload_apps()
    check('background refresh preserves reveal',reveal.tick_id is not None and app.dynamic==original_buttons)
    check('background refresh notifications coalesce',source is not None and app.apps_reload_source==source)
    yield 550
    check('background refresh runs after reveal',app.apps_reload_source is None and app.dynamic!=original_buttons)
    reveal.start()
    yield 40
    started = reveal.started
    state = Gdk.Event.new(Gdk.EventType.WINDOW_STATE)
    state.window_state.changed_mask = Gdk.WindowState.FOCUSED
    state.window_state.new_window_state = Gdk.WindowState.MAXIMIZED
    reveal.on_window_state(app.window, state.window_state)
    check('configure focus loss does not flash fully opaque', reveal.tick_id is not None and reveal.elapsed < reveal.DURATION)
    state.window_state.new_window_state = Gdk.WindowState.MAXIMIZED | Gdk.WindowState.FOCUSED
    reveal.on_window_state(app.window, state.window_state)
    check('configure focus return does not restart reveal', reveal.started == started)
    reveal.finish()
    check('desktop blends continuously into Apps', reveal_pose(0)[1] == 0 and 0 < reveal_pose(.12)[1] < 1)
    check('curve ends exactly at rest', reveal_pose(0.32) == (1.0, 1.0, 0.0))
    scales = [reveal_pose(t/1000)[0] for t in range(481)]
    check('scale settles without overshoot', scales == sorted(scales) and max(scales) == 1)
    bounds = geometry()
    samples = [snapshot(t) for t in (0.0, 0.08, 0.16, 0.32)]
    pixels = [bytes(s.get_data()) for s in samples]
    check('successive reveal frames visibly differ', len(set(pixels)) == 4)
    check('render transforms do not change hit targets', bounds == geometry())
    target = Path(os.environ.get('ROUND_MOTION_PREVIEW', '/tmp/aroundos-launchpad-motion.png'))
    contact = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1440, 360)
    cr = cairo.Context(contact)
    cr.scale(1/3, 1/3)
    for i, surface in enumerate(samples):
        cr.set_source_surface(surface, i*1080, 0)
        cr.paint()
    contact.write_to_png(str(target))
    reveal.finish()
    check('settled renderer matches native GTK', bytes(snapshot(reveal.DURATION).get_data()) == pixels[-1])
    count = len(frames)
    yield 150
    check('no idle animation callbacks', len(frames) == count)
    reveal.start()
    yield 80
    check('replay starts', reveal.tick_id is not None)
    check('window supports desktop blending', app.window.get_visual() == app.window.get_screen().get_rgba_visual())
    started = reveal.started
    reveal.start()
    check('duplicate activation does not restart motion', reveal.started == started)
    app.search.set_text('files')
    check('search interrupts animation', reveal.tick_id is None and app.query == 'files')
    app.search.set_text('')
    yield 80
    reveal.start()
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.key.window = app.window.get_window()
    event.key.keyval = Gdk.KEY_Page_Down
    event.set_device(Gdk.Display.get_default().get_default_seat().get_keyboard())
    Gtk.main_do_event(event)
    check('native keyboard paging interrupts reveal', reveal.tick_id is None)
    app.change_page(-1)
    yield 80
    app.window.iconify()
    yield 150
    check('minimize stops animation and arms return', reveal.tick_id is None and reveal.armed)
    count = len(frames)
    activate('aroundos-motion-check')
    yield 120
    check('restoring existing window replays reveal', len(frames) > count and reveal.tick_id is not None)
    yield 600
    check('restored window settles', reveal.tick_id is None and reveal.surface is None)
    os.environ['AROUNDOS_REDUCE_MOTION'] = '1'
    reduced = LaunchpadReveal()
    reduced.start()
    check('reduced motion skips animation', reduced.tick_id is None and reduced.elapsed == reduced.DURATION)
    reduced.destroy()
    del os.environ['AROUNDOS_REDUCE_MOTION']
    reveal.start()
    app.window.close()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    check('close removes animation callback', reveal.tick_id is None)


iterator = steps()


def tick():
    global failed
    try:
        delay = next(iterator)
        GLib.timeout_add(delay, tick)
    except StopIteration:
        pass
    except Exception:
        failed = True
        traceback.print_exc()
        if app.window:
            app.window.close()
    return False


app.connect('activate', lambda _: GLib.idle_add(tick))
app.run([])
intervals = [(b-a)/1000 for a,b in zip(frames, frames[1:]) if b-a < 100_000]
print(json.dumps({'passed': not failed, 'checks': len(checks),
                  'animation_frames': len(frames),
                  'median_frame_ms': round(statistics.median(intervals), 2) if intervals else None,
                  'median_draw_ms': round(statistics.median(draw_times), 2) if draw_times else None}))
raise SystemExit(1 if failed else 0)
