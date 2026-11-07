#!/usr/bin/env python3
"""Live desktop regression: hold timing, auto-repeat, lock and stop button.
Creates a brief recording on the Pi, validates it locally, then deletes it.
"""
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
import round_record as recorder
lock = recorder.lock_controller()
assert lock is not None, 'Stop the controller before this diagnostic'
controller = recorder.make_controller(lock)
controller.modified = lambda: False
from gi.repository import GLib, Gtk, Gdk
(recorder.STATE / 'recording.pid').write_text(str(os.getpid()))
panel = Gtk.Window()
panel.set_type_hint(Gdk.WindowTypeHint.UTILITY)
panel.set_name('PanelToplevel')
box = Gtk.Box()
clock = Gtk.Button(label='Clock fixture')
clock.set_name('clock')
box.add(clock)
panel.add(box)
panel.show_all()
started = time.monotonic()
phase = 0
failure = []
controller.key(-1, 99, 1)

def check():
    global phase
    try:
        elapsed = time.monotonic() - started
        if elapsed > 45:
            raise AssertionError('Recording/export timed out')
        # Real evdev repeat values delivered while Print remains held.
        if phase < 3:
            controller.key(-1, 99, 2)
            controller.key(-1, 99, 1)  # Duplicate press is also ignored.
        if phase == 0 and elapsed > 1:
            for _ in range(8):
                subprocess.run([sys.executable, str(recorder.HERE / 'round_record.py'), '--daemon'], check=True, timeout=2)
            assert controller.state == 'idle' and controller.child is None
            print('PASS: duplicate controller starts ignored', flush=True)
            phase = 1
        if phase == 1 and controller.state == 'countdown':
            assert 3.9 <= elapsed < 4.4, elapsed
            assert controller.child is None
            print('PASS: countdown begins at four seconds', round(elapsed, 2), flush=True)
            phase = 2
        if phase == 2 and controller.state == 'recording':
            assert 7.1 <= elapsed < 8, elapsed
            assert controller.child.poll() is None
            print('PASS: recording starts after countdown', round(elapsed, 2), flush=True)
            phase = 3
        if phase == 3 and elapsed > 8.5:
            controller.key(-1, 99, 0)
            assert controller.state == 'recording'
            for _ in range(8):
                subprocess.run([sys.executable, str(recorder.HERE / 'round_record.py')], check=True, timeout=2)
            assert controller.child.poll() is None
            dot = next(w for w in box.get_children() if w.get_name() == 'aroundos-recording-dot')
            assert dot.get_visible()
            dot.emit('clicked')
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            assert controller.sheet.get_visible()
            size = controller.sheet.get_size()
            assert size.width <= 700 and size.height <= 500, size
            controller.save_button.emit('clicked')
            assert controller.state == 'stopping'
            print('PASS: toolbar dot opens editor-style sheet; Stop saves', flush=True)
            phase = 4
        if phase == 4 and controller.state == 'saving':
            assert controller.feedback.get_visible()
            assert controller.feedback_title.get_text() == 'Saving screen recording…'
            assert not controller.open_recordings.get_visible()
            child = controller.child.pid
            controller.key(-1, 99, 1)
            controller.key(-1, 99, 0)
            assert controller.state == 'saving' and controller.child.pid == child
            print('PASS: export blocks new recordings', flush=True)
            phase = 5
        if phase == 5 and controller.state == 'idle':
            assert controller.feedback.get_visible()
            assert controller.feedback_title.get_text() == 'Screen recording saved'
            assert controller.open_recordings.get_visible()
            duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(controller.final)], text=True))
            assert 0 < duration < 5, duration
            assert not controller.raw.exists()
            controller.final.unlink()
            print('PASS: finite export and test recording deleted', flush=True)
            controller.set_state('starting')
            controller.start()
            controller.test_delete_at = time.monotonic() + 1.5
            phase = 6
        if phase == 6 and time.monotonic() >= controller.test_delete_at:
            controller.show_menu()
            controller.delete_button.emit('clicked')
            assert controller.state == 'stopping'
            phase = 7
        if phase == 7 and controller.state == 'idle':
            assert all(not p.exists() for p in (controller.raw, controller.partial, controller.final))
            controller.key(-1, 99, 1)
            controller.clear_hold()
            controller.held()
            assert controller.state == 'countdown'
            controller.key(-1, 99, 0)
            controller.key(-1, 99, 1)
            assert controller.state == 'idle' and controller.child is None
            print('PASS: Delete discards capture; countdown cancels cleanly', flush=True)
            Gtk.main_quit()
            return False
    except BaseException as error:
        failure.append(repr(error))
        if controller.child and controller.child.poll() is None:
            controller.child.kill()
            controller.child.wait()
        for name in ('raw', 'partial', 'final'):
            path = getattr(controller, name, None)
            if path:
                path.unlink(missing_ok=True)
        Gtk.main_quit()
        return False
    return True
GLib.timeout_add(20, check)
Gtk.main()
lock.close()
(recorder.STATE / 'recording.pid').unlink(missing_ok=True)
if failure:
    raise SystemExit(failure)
