#!/usr/bin/env python3
"""One desktop controller owns Print Screen, countdown, recording and export."""
import datetime
import fcntl
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
STATE = Path.home() / '.local/state/aroundos-round'
PRINT = {99, 210}
MODIFIERS = {29, 97, 42, 54, 56, 100, 125, 126}
EVENT = struct.Struct('llHHi')


def lock_controller():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open(STATE / 'recording.lock', 'a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock  # Never unlink this inode. Children retain the lock if we crash.


def stop_existing():
    try:
        pid = int((STATE / 'recording.pid').read_text())
        args = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
        if any(a.endswith(b'/round_record.py') for a in args):
            os.kill(pid, signal.SIGUSR1)
    except (OSError, ValueError):
        pass


def make_controller(lock):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib

    class Controller:
        def __init__(self):
            self.state = 'idle'
            self.devices = {}
            self.pressed = set()
            self.hold_timer = None
            self.count_timer = None
            self.child = None
            self.log = None
            self.quitting = False
            self.count_window = Gtk.Window(title='Recording countdown · AroundOS')
            self.count_window.set_decorated(False)
            self.count_window.set_skip_taskbar_hint(True)
            self.count_window.set_keep_above(True)
            self.count_window.fullscreen()
            self.number = Gtk.Label(label='3')
            self.number.set_name('record-countdown')
            self.count_window.add(self.number)
            self.count_window.connect('delete-event', lambda *_: self.cancel_countdown() or True)
            self.count_window.connect('map-event', self.count_mapped)
            from round_editor import CSS as EDITOR_CSS
            from round_ui import SHELL_CSS
            self.sheet = Gtk.Window(title='Screen recording · AroundOS')
            self.sheet.set_name('round-shell')
            self.sheet.set_type_hint(Gdk.WindowTypeHint.DIALOG)
            self.sheet.set_decorated(False)
            self.sheet.set_keep_above(True)
            self.sheet.set_skip_taskbar_hint(True)
            self.sheet.set_position(Gtk.WindowPosition.CENTER)
            self.sheet.set_resizable(False)
            self.sheet.connect('delete-event', lambda *_: self.sheet.hide() or True)
            self.sheet.connect('key-press-event', lambda _, event: (self.sheet.hide() or True) if event.keyval == Gdk.KEY_Escape else False)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_size_request(580, -1)
            box.get_style_context().add_class('save-sheet')
            heading = Gtk.Label(label='Screen recording', xalign=0)
            heading.get_style_context().add_class('filename')
            box.add(heading)
            self.save_button = Gtk.Button(label='Stop screen recording')
            self.delete_button = Gtk.Button(label='Delete')
            cancel = Gtk.Button(label='Keep recording')
            for button in (self.save_button, self.delete_button, cancel):
                button.set_size_request(-1, 62)
                button.get_style_context().add_class('action')
                box.add(button)
            self.save_button.get_style_context().add_class('accent')
            self.delete_button.get_style_context().add_class('record-delete')
            self.save_button.connect('clicked', lambda *_: self.stop())
            self.delete_button.connect('clicked', lambda *_: self.discard())
            cancel.connect('clicked', lambda *_: self.sheet.hide())
            self.sheet.add(box)
            self.feedback = Gtk.Window(title='Recording saved · AroundOS')
            self.feedback.set_name('round-shell')
            self.feedback.set_type_hint(Gdk.WindowTypeHint.DIALOG)
            self.feedback.set_decorated(False)
            self.feedback.set_keep_above(True)
            self.feedback.set_skip_taskbar_hint(True)
            self.feedback.set_position(Gtk.WindowPosition.CENTER)
            self.feedback.set_resizable(False)
            self.feedback.connect('delete-event', lambda *_: self.feedback.hide() or True)
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            info.set_size_request(580, -1)
            info.get_style_context().add_class('save-sheet')
            self.feedback_title = Gtk.Label(xalign=0)
            self.feedback_title.get_style_context().add_class('filename')
            self.feedback_detail = Gtk.Label(xalign=0)
            self.feedback_detail.set_line_wrap(True)
            self.feedback_detail.set_max_width_chars(40)
            info.add(self.feedback_title)
            info.add(self.feedback_detail)
            self.open_recordings = Gtk.Button(label='Open recordings')
            self.open_recordings.connect('clicked', lambda *_: subprocess.Popen(['xdg-open', str(Path.home() / 'Videos/Recordings')]))
            self.dismiss = Gtk.Button(label='Close')
            self.dismiss.connect('clicked', lambda *_: self.feedback.hide())
            for button in (self.open_recordings, self.dismiss):
                button.set_size_request(-1, 62)
                button.get_style_context().add_class('action')
                info.add(button)
            self.feedback.add(info)
            css = Gtk.CssProvider()
            css.load_from_data(SHELL_CSS + EDITOR_CSS + b'#record-countdown { color:#e8eeeb; font:bold 240px "Rubik", Sans; } #round-shell .record-delete { color:#ff6969; }')
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.stop)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self.show_menu)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit)
            self.discover()
            GLib.timeout_add_seconds(2, self.discover)
            self.set_state('idle')

        def set_state(self, state):
            self.state = state
            (STATE / 'recording.status').write_text(state + '\n')

        def show_feedback(self, title, detail, saving=False):
            self.feedback_title.set_text(title)
            self.feedback_detail.set_text(detail)
            self.dismiss.set_label('Keep working' if saving else 'Close')
            self.feedback.show_all()
            self.open_recordings.set_visible(not saving)
            self.feedback.present()

        def discover(self):
            for path in Path('/dev/input').glob('event*'):
                if str(path) in self.devices:
                    continue
                fd = None
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    keys = bytearray(96)
                    fcntl.ioctl(fd, 0x80000000 | (96 << 16) | (ord('E') << 8) | 0x21, keys)
                    if not any(keys[k // 8] & (1 << (k % 8)) for k in PRINT):
                        os.close(fd)
                        continue
                    self.devices[str(path)] = fd
                    GLib.io_add_watch(fd, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.input_ready, str(path))
                except OSError:
                    if fd is not None:
                        os.close(fd)
            return True

        def input_ready(self, fd, condition, path):
            try:
                if condition & (GLib.IO_HUP | GLib.IO_ERR):
                    raise OSError('Keyboard disconnected')
                data = os.read(fd, EVENT.size * 64)
                if not data:
                    raise OSError('Keyboard disconnected')
                for offset in range(0, len(data), EVENT.size):
                    _, _, kind, code, value = EVENT.unpack_from(data, offset)
                    if kind == 1 and code in PRINT:
                        self.key(fd, code, value)
                return True
            except BlockingIOError:
                return True
            except OSError:
                self.devices.pop(path, None)
                os.close(fd)
                self.pressed = {key for key in self.pressed if key[0] != fd}
                self.clear_hold()
                return False

        def modified(self):
            for fd in self.devices.values():
                keys = bytearray(96)
                try:
                    fcntl.ioctl(fd, 0x80000000 | (96 << 16) | (ord('E') << 8) | 0x18, keys)
                    if any(keys[k // 8] & (1 << (k % 8)) for k in MODIFIERS):
                        return True
                except OSError:
                    pass
            return False

        def key(self, fd, code, value):
            key = (fd, code)
            if value == 2:  # Keyboard auto-repeat never causes an action.
                return
            if value == 1:
                if key in self.pressed or self.modified():
                    return
                was_pressed = bool(self.pressed)
                self.pressed.add(key)
                if was_pressed:
                    return
                if self.state == 'idle':
                    self.hold_timer = GLib.timeout_add(4000, self.held)
                elif self.state in ('countdown', 'starting', 'recording'):
                    self.stop()
                # Saving is busy: no new sessions or queued captures.
            elif value == 0 and key in self.pressed:
                self.pressed.remove(key)
                if not self.pressed and self.hold_timer is not None:
                    self.clear_hold()
                    if self.state == 'idle':
                        self.set_state('screenshot')
                        self.child = subprocess.Popen(['/usr/bin/python3', str(HERE / 'round_screenshot.py')], pass_fds=(lock.fileno(),))
                        GLib.timeout_add(100, self.poll)

        def clear_hold(self):
            if self.hold_timer is not None:
                GLib.source_remove(self.hold_timer)
                self.hold_timer = None

        def held(self):
            self.hold_timer = None
            if self.pressed and self.state == 'idle':
                self.feedback.hide()
                self.set_state('countdown')
                self.count = 3
                self.number.set_text('3')
                self.count_window.show_all()
            return False

        def count_mapped(self, *_):
            if self.state == 'countdown' and self.count_timer is None:
                self.count_timer = GLib.timeout_add(1000, self.tick)
            return False

        def tick(self):
            self.count -= 1
            if self.count:
                self.number.set_text(str(self.count))
                return True
            self.count_timer = None
            self.count_window.hide()
            Gdk.Display.get_default().sync()
            self.set_state('starting')
            GLib.timeout_add(200, self.start)
            return False

        def cancel_countdown(self):
            if self.count_timer is not None:
                GLib.source_remove(self.count_timer)
                self.count_timer = None
            self.count_window.hide()
            self.set_state('idle')

        def start(self):
            if self.state != 'starting':
                return False
            videos = Path.home() / 'Videos/Recordings'
            videos.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')
            self.raw = videos / f'.Recording_{stamp}.mkv'
            self.final = videos / f'Recording_{stamp}.webm'
            self.partial = videos / f'.Recording_{stamp}.webm'
            self.discard_requested = False
            self.started_at = time.monotonic()
            self.log = open(STATE / 'recording.log', 'w')
            try:
                self.child = subprocess.Popen(['nice', '-n', '10', str(Path.home() / '.local/bin/wf-recorder'), '-o', 'HDMI-A-1', '-D', '-r', '24', '-p', 'threads=2', '-f', str(self.raw)], stdout=self.log, stderr=self.log, pass_fds=(lock.fileno(),))
                self.set_state('recording')
                GLib.timeout_add(100, self.poll)
            except OSError as error:
                self.failed(error)
            return False

        def show_menu(self):
            if self.state == 'recording':
                self.sheet.show_all()
                self.sheet.present()
            elif self.state in ('stopping', 'saving'):
                self.show_feedback('Saving screen recording…', 'Finishing the circular video. You can keep working while it saves.', True)
            return True

        def discard(self):
            if self.state == 'recording':
                self.discard_requested = True
                self.stop()

        def stop(self):
            self.clear_hold()
            if self.state in ('countdown', 'starting'):
                self.cancel_countdown()
            elif self.state == 'recording':
                self.set_state('stopping')
                self.sheet.hide()
                self.stop_time = time.monotonic()
                if self.child.poll() is None:
                    self.child.send_signal(signal.SIGINT)
            return True

        def poll(self):
            if self.child.poll() is None:
                if self.state == 'stopping' and time.monotonic() - self.stop_time > 10:
                    self.child.kill()
                return True
            code = self.child.returncode
            self.child = None
            if self.state == 'screenshot':
                self.set_state('idle')
            elif self.state in ('recording', 'stopping'):
                self.sheet.hide()
                if self.discard_requested:
                    for path in (self.raw, self.partial, self.final):
                        path.unlink(missing_ok=True)
                    self.set_state('idle')
                elif code != 0:
                    self.failed('Capture failed; see recording.log')
                else:
                    self.export()
                    return self.child is not None
            elif self.state == 'saving':
                if code == 0:
                    try:
                        self.partial.replace(self.final)
                        self.raw.unlink(missing_ok=True)
                        self.set_state('idle')
                        self.show_feedback('Screen recording saved', 'Saved in Videos → Recordings\n' + self.final.name)
                    except OSError as error:
                        self.failed(error)
                else:
                    self.failed('Export failed; original capture retained')
            if self.log:
                self.log.close()
                self.log = None
            if self.quitting:
                Gtk.main_quit()
            return False

        def export(self):
            self.set_state('saving')
            self.show_feedback('Saving screen recording…', 'Finishing the circular video. You can keep working while it saves.', True)
            try:
                duration_text = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(self.raw)], text=True).strip()
                duration = float(duration_text) if duration_text != 'N/A' else max(.05, getattr(self, 'stop_time', time.monotonic()) - self.started_at)
                command = ['nice', '-n', '19', 'ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-threads', '1', '-i', str(self.raw), '-loop', '1', '-i', str(HERE / 'record-mask.png'), '-filter_complex_threads', '1', '-filter_complex', '[0:v]format=rgba[v];[v][1:v]alphamerge=shortest=1[out]', '-map', '[out]', '-an', '-c:v', 'libvpx-vp9', '-threads', '1', '-deadline', 'realtime', '-cpu-used', '8', '-b:v', '3M', '-pix_fmt', 'yuva420p', '-t', str(duration), str(self.partial)]
                self.child = subprocess.Popen(command, stdout=self.log, stderr=self.log, pass_fds=(lock.fileno(),))
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                self.failed(error)

        def failed(self, error):
            print(error, file=sys.stderr, flush=True)
            self.sheet.hide()
            self.set_state('idle')
            self.show_feedback('Recording could not be saved', str(error) + '\nAny original capture has been kept in Videos/Recordings.')
            if self.log:
                self.log.close()
                self.log = None

        def quit(self):
            self.quitting = True
            self.stop()
            if self.child is None:
                Gtk.main_quit()
            return True

    return Controller()


def main():
    if '--stop' in sys.argv:
        stop_existing()
        return
    lock = lock_controller()
    if lock is None:
        return
    controller = make_controller(lock)
    from gi.repository import Gtk
    (STATE / 'recording.pid').write_text(str(os.getpid()))
    try:
        Gtk.main()
    finally:
        (STATE / 'recording.pid').unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    main()
