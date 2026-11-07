"""A short, frame-clock driven entrance for the native Launchpad grid."""
import os
import ctypes
import logging

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

# Raspberry Pi OS ships Pycairo without the optional gi-cairo converter. Use
# the public GTK/Cairo C drawing API, as the desktop's native glass module does,
# so this small effect needs no package installation or private Python ABI.
_gtk = ctypes.CDLL('libgtk-3.so.0')
_gobject = ctypes.CDLL('libgobject-2.0.so.0')
_cairo = ctypes.CDLL('libcairo.so.2')
_ptr = ctypes.c_void_p
_double = ctypes.c_double
_DRAW = ctypes.CFUNCTYPE(ctypes.c_int, _ptr, _ptr, _ptr)


def _bind(library, name, args, result=None):
    function = getattr(library, name)
    function.argtypes, function.restype = args, result
    return function


_connect = _bind(_gobject, 'g_signal_connect_data', [_ptr, ctypes.c_char_p, _DRAW, _ptr, _ptr, ctypes.c_int], ctypes.c_ulong)
_disconnect = _bind(_gobject, 'g_signal_handler_disconnect', [_ptr, ctypes.c_ulong])
_propagate = _bind(_gtk, 'gtk_container_propagate_draw', [_ptr, _ptr, _ptr])
_save = _bind(_cairo, 'cairo_save', [_ptr])
_restore = _bind(_cairo, 'cairo_restore', [_ptr])
_translate = _bind(_cairo, 'cairo_translate', [_ptr, _double, _double])
_scale = _bind(_cairo, 'cairo_scale', [_ptr, _double, _double])
_surface_create = _bind(_cairo, 'cairo_image_surface_create', [ctypes.c_int]*3, _ptr)
_surface_destroy = _bind(_cairo, 'cairo_surface_destroy', [_ptr])
_context_create = _bind(_cairo, 'cairo_create', [_ptr], _ptr)
_context_destroy = _bind(_cairo, 'cairo_destroy', [_ptr])
_source_rgb = _bind(_cairo, 'cairo_set_source_rgb', [_ptr, _double, _double, _double])
_source_surface = _bind(_cairo, 'cairo_set_source_surface', [_ptr, _ptr, _double, _double])
_paint = _bind(_cairo, 'cairo_paint', [_ptr])
_operator = _bind(_cairo, 'cairo_set_operator', [_ptr, ctypes.c_int])
_rgba = _bind(_cairo, 'cairo_set_source_rgba', [_ptr, _double, _double, _double, _double])
_alpha = _bind(_cairo, 'cairo_paint_with_alpha', [_ptr, _double])


def reveal_pose(elapsed):
    """A 320 ms unified reveal, composited over the live desktop."""
    t = max(0.0, min(1.0, elapsed / 0.32))
    remaining = (1.0 - t) ** 3
    return 1.0 - 0.06 * remaining, 1.0 - remaining, remaining


class LaunchpadReveal(Gtk.Fixed):
    """Transform drawing only, leaving GTK's layout and accessibility intact.

    Any input finishes the reveal before GTK dispatches it, so the real hit
    targets always match what the user sees. A single cached layer keeps all elements moving together.
    """
    DURATION = 0.32

    def __init__(self):
        super().__init__()
        self.tick_id = None
        self.started = None
        self.elapsed = self.DURATION
        self.armed = True
        self.surface = None
        self.window = None
        # The desktop deliberately disables global GTK transitions. This local
        # effect is opt-out without turning unrelated GTK animations back on.
        self.reduced_motion = os.environ.get('AROUNDOS_REDUCE_MOTION', '').lower() in ('1', 'true', 'yes')
        self._draw_callback = _DRAW(self.draw_native)
        self._draw_handler = None
        self.connect('unmap', lambda *_: self.finish())
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, *_):
        self.finish()
        if self._draw_handler:
            _disconnect(hash(self.window), self._draw_handler)
            self._draw_handler = None

    def attach(self, window):
        self.window = window
        visual = window.get_screen().get_rgba_visual()
        if visual:
            window.set_visual(visual)
        # GTK paints the opaque shell background when native drawing resumes.
        self._draw_handler = _connect(hash(window), b'draw', self._draw_callback, None, None, 0)
        window.connect('map', self.on_map)
        window.connect('window-state-event', self.on_window_state)
        window.connect('event', self.on_input)

    def on_map(self, *_):
        self.armed = False
        self.start()

    def on_window_state(self, window, event):
        if event.new_window_state & Gdk.WindowState.ICONIFIED:
            self.armed = True
            self.finish()
        elif event.changed_mask & Gdk.WindowState.FOCUSED:
            if event.new_window_state & Gdk.WindowState.FOCUSED:
                if self.armed:
                    self.armed = False
                    self.start()
            else:
                # labwc briefly removes FOCUSED between map and maximize.
                # Finishing here presents an opaque frame before focus returns,
                # then restarts at zero: the visible full-screen flash.
                # Let an in-flight reveal survive this configure handshake.
                if self.tick_id is None:
                    self.armed = True
        return False

    def on_input(self, window, event):
        # The finger opening Apps can still be down over the dock/top bar when
        # this window maps. Do not treat that contact (or its emulated mouse
        # press) as a new action inside Apps. Actual controls/grid gestures
        # finish the reveal in their own handlers.
        if event.type in (Gdk.EventType.KEY_PRESS, Gdk.EventType.SCROLL):
            self.finish()
        return False

    def start(self):
        if self.tick_id is not None:
            return
        self.finish()
        if self.reduced_motion:
            return
        self.started = None
        self.elapsed = 0.0
        self.tick_id = self.add_tick_callback(self.advance)
        (self.window or self).queue_draw()

    def finish(self):
        if self.tick_id is not None:
            self.remove_tick_callback(self.tick_id)
            self.tick_id = None
        self.started = None
        self.elapsed = self.DURATION
        self.release_surface()
        (self.window or self).queue_draw()

    def advance(self, widget, clock):
        now = clock.get_frame_time()
        # First-time icon/text rasterization can consume several frames on Pi.
        # Do not spend the opening animation's clock while building its layer.
        if self.surface is None:
            self.started = None
            self.elapsed = 0.0
            (self.window or self).queue_draw()
            return True
        if self.started is None:
            self.started = now
        self.elapsed = (now - self.started) / 1_000_000
        (self.window or self).queue_draw()
        if self.elapsed >= self.DURATION:
            self.tick_id = None
            self.started = None
            self.elapsed = self.DURATION
            self.release_surface()
            return False
        return True

    def draw_native(self, widget, cr, data):
        if self.elapsed >= self.DURATION:
            return False
        _save(cr)
        try:
            self.paint_children(cr)
        except Exception:
            # ctypes callbacks must never let exceptions cross the C boundary.
            logging.exception('Launchpad reveal stopped; restoring native drawing')
            self.finish()
            return False
        finally:
            _restore(cr)
        return True

    def release_surface(self):
        if self.surface is not None:
            _surface_destroy(self.surface)
            self.surface = None

    def paint_children(self, cr):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        if self.surface is None:
            # Render GTK once at its final geometry. Reusing this opaque layer
            # avoids per-icon alpha composition and partial-child redraw flashes.
            self.surface = _surface_create(0, width, height)
            context = _context_create(self.surface)
            try:
                _source_rgb(context, 16/255, 16/255, 18/255)
                _paint(context)
                for child in self.get_children():
                    if child.get_visible() and child.get_child_visible():
                        _propagate(hash(self), hash(child), context)
            finally:
                _context_destroy(context)
        scale, opacity, _ = reveal_pose(self.elapsed)
        # Replace the whole RGBA frame directly with one composited layer.
        # SOURCE avoids reading/blending the previous full-screen buffer.
        _operator(cr, 1)  # CAIRO_OPERATOR_SOURCE
        _translate(cr, width / 2, height / 2)
        _scale(cr, scale, scale)
        _translate(cr, -width / 2, -height / 2)
        _source_surface(cr, self.surface, 0, 0)
        _alpha(cr, opacity)
