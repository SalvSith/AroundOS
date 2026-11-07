#!/usr/bin/env python3
"""Run on the Pi desktop; generate real clips and exercise playback and cleanup."""
from pathlib import Path
import hashlib
import math
import subprocess
import sys
import tempfile
import time
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/round-desktop'))
from round_videos import Videos, Gst, Gio, GLib, clock_text

checks = []
failed = False

def check(name, result):
    if not result: raise AssertionError(name)
    checks.append(name)

def geometry(app):
    check('1080 client', (app.window.get_allocated_width(),app.window.get_allocated_height()) == (1080,1080))
    for widget in app.placed:
        if not widget.get_visible(): continue
        x, y = widget.translate_coordinates(app.window, 0, 0)
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        check('circle bounds', max(math.hypot(px-540, py-540) for px in (x,x+w) for py in (y,y+h)) <= 535)

with tempfile.TemporaryDirectory(prefix='aroundos-video-fixtures-') as folder:
    paths = []
    for name, codec in [('01 sample ü.mp4', 'mpeg4'), ('02 sample.webm', 'libvpx'), ('03 sample.mkv', 'mpeg4')]:
        path = Path(folder) / name
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=320x180:rate=15', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                        '-t', '4', '-c:v', codec, '-c:a', 'libvorbis' if path.suffix == '.webm' else 'aac', str(path)], check=True)
        paths.append(path)
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    app = Videos(); app.set_application_id('org.aroundos.VideosCheck'); app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    def steps():
        yield None
        geometry(app)
        check('empty controls disabled', not app.play_button.get_sensitive())
        check('clock formatting', clock_text(3661) == '1:01:01' and clock_text(65) == '1:05')
        for path in paths:
            app.open_path(path)
            yield lambda: app.ready and app.duration > 0
            check('decodes '+path.suffix, app.player.query_position(Gst.Format.TIME)[0])
            check('audio stream selected', app.player.get_property('n-audio') == 1)
            app.toggle(); yield None
            check('pause', app.player.get_state(0)[1] == Gst.State.PAUSED)
            check('seek', app.seek_to(2))
            yield None
            check('seek position', app.player.query_position(Gst.Format.TIME)[1] >= Gst.SECOND)
            app.volume.set_value(0.25)
            check('volume', abs(app.player.get_property('volume')-0.25)<0.01)
            app.fullscreen(); yield None
            check('fullscreen', app.immersive and not app.play_button.get_visible())
            geometry(app)
            app.tap.emit('released',1,400.0,400.0); yield None
            check('tap exits fullscreen', not app.immersive and app.play_button.get_visible())
            geometry(app)
        app.open_path(paths[0]); yield lambda: app.ready
        app.step(1); yield lambda: app.ready
        check('next video', app.path == paths[1])
        app.step(-1); yield lambda: app.ready
        check('previous video', app.path == paths[0])
        app.open_path(paths[0]); app.open_path(paths[2]); yield lambda: app.ready
        check('rapid replacement', app.path == paths[2])
        yield lambda: app.ended
        check('end stops', not app.playing)
        app.toggle(); yield None
        check('replay', app.playing and not app.ended)
        app.open_path(Path(folder)/'missing.mp4'); yield None
        check('missing file', app.player is None and not app.play_button.get_sensitive())
        bad = Path(folder)/'broken.mp4'; bad.write_bytes(b'not a video')
        app.open_path(bad); yield lambda: app.player is None
        check('corrupt file error', app.message.get_visible())
        app.open_path(paths[0]); yield lambda: app.ready
        check('recovers after error', app.ready)
        check('source files unchanged', hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])
        app.toggle(); yield None
        subprocess.run(['grim', '/tmp/aroundos-videos.png'], check=True)
    iterator = steps(); pending = None; deadline = time.monotonic()+20
    def tick():
        global pending, deadline, failed
        try:
            if pending and not pending():
                if time.monotonic()>deadline: raise TimeoutError('Playback did not settle: '+app.message.get_text())
                return True
            pending = next(iterator); deadline = time.monotonic()+20
            return True
        except StopIteration: pass
        except Exception: failed = True; traceback.print_exc()
        app.window.close()
        return False
    app.connect('activate', lambda *_: GLib.timeout_add(350, tick))
    app.run([sys.argv[0]])
    check('pipeline and timer released', app.player is None and app.timer is None)
print(f'{len(checks)} video checks passed' if not failed else 'Video checks FAILED')
sys.exit(1 if failed else 0)
