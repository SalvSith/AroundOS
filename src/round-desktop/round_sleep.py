"""Power off the home display, consuming the first input used to wake it."""
import ctypes
import fcntl
import os
from pathlib import Path
import signal
import subprocess

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk


def main():
    lock = (Path(os.environ['XDG_RUNTIME_DIR']) / 'aroundos-screen-sleep.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    layer = ctypes.CDLL('libgtk-layer-shell.so.0')
    for name, args in (
        ('gtk_layer_init_for_window', [ctypes.c_void_p]),
        ('gtk_layer_set_layer', [ctypes.c_void_p, ctypes.c_int]),
        ('gtk_layer_set_anchor', [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
        ('gtk_layer_set_keyboard_mode', [ctypes.c_void_p, ctypes.c_int]),
        ('gtk_layer_set_exclusive_zone', [ctypes.c_void_p, ctypes.c_int]),
    ):
        getattr(layer, name).argtypes = args
        getattr(layer, name).restype = None
    window = Gtk.Window(title='Screen sleep')
    pointer = hash(window)
    layer.gtk_layer_init_for_window(pointer)
    layer.gtk_layer_set_layer(pointer, 3)  # Overlay, above both bars.
    for edge in range(4):
        layer.gtk_layer_set_anchor(pointer, edge, True)
    layer.gtk_layer_set_exclusive_zone(pointer, -1)
    layer.gtk_layer_set_keyboard_mode(pointer, 1)
    css = Gtk.CssProvider()
    css.load_from_data(b'window { background: #000; background-image: none; }')
    window.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window.add_events(Gdk.EventMask.TOUCH_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.KEY_RELEASE_MASK)
    waking = False

    def wake(*args):
        nonlocal waking
        if not waking:
            waking = True
            # Retain the shield briefly while the wake input finishes.
            GLib.timeout_add(350, lambda: (Gtk.main_quit(), False)[1])
        return True

    window.connect('button-release-event', wake)
    window.connect('key-release-event', wake)
    window.connect('touch-event', lambda widget, event: wake() if event.type in (Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL) else True)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, wake)
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, wake)
    window.show_all()
    idle = None
    try:
        # Idle notification wakes even when the powered-off output receives no
        # client touch events. Delay sleep until the launch tap has finished.
        idle = subprocess.Popen([
            'swayidle', '-w', 'timeout', '1', 'wlopm --off HDMI-A-1',
            'resume', f'wlopm --on HDMI-A-1; kill -USR1 {os.getpid()}',
        ])
        def check_idle():
            if idle.poll() is not None:
                wake()
                return False
            return True
        GLib.timeout_add(250, check_idle)
        Gtk.main()
    finally:
        if idle is not None and idle.poll() is None:
            idle.terminate()
            try:
                idle.wait(timeout=3)
            except subprocess.TimeoutExpired:
                idle.kill()
                idle.wait()
        subprocess.run(['wlopm', '--on', 'HDMI-A-1'], check=False, timeout=3)
        window.destroy()


if __name__ == '__main__':
    main()
