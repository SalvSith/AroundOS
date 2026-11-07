#!/usr/bin/env python3
"""Portable URL/geometry checks. --live also exercises the real WebKit engine."""
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/round-desktop'))
spec = importlib.util.spec_from_file_location('round_browser', ROOT / 'src/round-desktop/round_browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
cases = {
    '': None, ' example.com ': 'https://example.com',
    'https://example.com/a?q=1': 'https://example.com/a?q=1',
    'localhost:8000': 'http://localhost:8000',
    '127.0.0.1:8080/test': 'http://127.0.0.1:8080/test',
    '[::1]:8000': 'http://[::1]:8000',
    'http://[': 'https://duckduckgo.com/?q=http%3A%2F%2F%5B',
    'round screen': 'https://duckduckgo.com/?q=round%20screen',
    'javascript:alert(1)': 'https://duckduckgo.com/?q=javascript%3Aalert%281%29',
    'file:///etc/passwd': 'https://duckduckgo.com/?q=file%3A%2F%2F%2Fetc%2Fpasswd',
}
for text, expected in cases.items():
    assert browser.address_uri(text) == expected, text
rects = [(278,182,524,56), (280,256,520,30)]
rects += [(*browser.control_position(i),56,56) for i in range(5)]
for x,y,w,h in rects:
    for px,py in ((x,y),(x+w,y),(x,y+h),(x+w,y+h)):
        assert math.hypot(px-540,py-540) <= 515, (x,y,w,h,px,py)
x,y,w,h = browser.PAGE_BOUNDS
assert w > 772 and w*h >= 772*650
assert y+h == 1080 and (x,w) == (90,900)
for source in [ROOT/'src/round-desktop/round_browser.py', ROOT/'scripts/install-round-browser.py']:
    compile(source.read_text(), str(source), 'exec')
print('URL parsing, source compilation and circular bounds passed.')

if '--live' in sys.argv:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gtk, GLib, WebKit2
    from gi.repository import Gio
    original_run = Gtk.Application.run
    failures = []
    def checked_run(app, argv):
        app.set_application_id('org.aroundos.BrowserCheck')
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        def geometry():
            assert len(app.placed) == 10, 'Browser did not finish building'
            for widget in app.placed:
                if isinstance(widget, Gtk.Image):
                    continue
                a = widget.get_allocation()
                x, y = widget.translate_coordinates(app.window, 0, 0)
                if widget is app.web:
                    assert (x,y,a.width,a.height) == browser.PAGE_BOUNDS
                    assert y+a.height == 1080
                else:
                    assert max(math.hypot(px-540, py-540) for px in (x,x+a.width) for py in (y,y+a.height)) <= 515
        def steps():
            yield lambda: app.page_rgb == (16,16,18)
            geometry()
            app.web.load_html('<body style="background:#f4efdf;color:#222"><h1>Light canvas</h1><p>Content reaches into the sides.</p>', 'about:blank')
            yield lambda: app.page_rgb == (244,239,223)
            geometry()
            subprocess.run(['grim', '/tmp/aroundos-browser-light.png'], check=True)
            app.web.load_html('<html style="background:#183044"><body style="background:transparent;color:white"><h1>Dark canvas</h1></body></html>', 'about:blank')
            yield lambda: app.page_rgb == (24,48,68)
            subprocess.run(['grim', '/tmp/aroundos-browser-dark.png'], check=True)
            app.web.evaluate_javascript("document.body.style.backgroundColor = 'rgb(90, 50, 70)'", -1, None, None, None, None, None)
            yield lambda: app.page_rgb == (90,50,70)
            app.web.load_html('<body><h1>Default canvas</h1>', 'about:blank')
            yield lambda: app.page_rgb == (255,255,255)
            app.web.load_html('<html style="background:rgb(20,40,60)"><body style="min-height:100vh;background:rgba(100,120,140,.5)">Alpha</body></html>', 'about:blank')
            yield lambda: app.page_rgb == (60,80,100)
            app.web.load_html('<body style="margin:0;background:white"><main style="min-height:100vh;background:rgb(32,38,44);color:white"><h1>App wrapper</h1><p style="padding-top:650px">Page continues behind the toolbar.</p></main>', 'about:blank')
            yield lambda: app.page_rgb == (32,38,44)
            geometry()
            subprocess.run(['grim', '/tmp/aroundos-browser-wrapper.png'], check=True)
            app.web.load_html('<body style="margin:0;background:white"><main style="min-height:100vh;background:color(srgb 0.2 0.4 0.6)">Modern CSS colour</main>', 'about:blank')
            yield lambda: app.page_rgb == (51,102,153)
            app.web.load_html('<body style="background:red">Previous</body>', 'about:blank')
            app.home()
            yield lambda: app.page_rgb == (16,16,18)
            geometry()
            print('Actual viewport bounds, light/dark/transparent canvases, live theme changes and navigation reset passed.')
        sequence = steps()
        pending = None
        deadline = time.monotonic()+15
        def inspect():
            nonlocal pending, deadline
            try:
                if pending is not None and not pending():
                    assert time.monotonic() < deadline, f'Canvas update timed out: {app.page_rgb}'
                    return True
                pending = next(sequence)
                deadline = time.monotonic()+15
                return True
            except StopIteration:
                pass
            except Exception as error:
                failures.append(error)
            app.window.close()
            return False
        app.connect('activate', lambda _: GLib.timeout_add(400, inspect))
        result = original_run(app, [])
        assert app.appearance_timer is None
        return result
    Gtk.Application.run = checked_run
    try:
        browser.main()
    finally:
        Gtk.Application.run = original_run
    assert not failures, failures
    view = WebKit2.WebView()
    view.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
    window = Gtk.Window()
    window.add(view)
    window.show_all()
    done = []
    def loaded(view, event):
        if event == WebKit2.LoadEvent.FINISHED:
            done.append(True)
            Gtk.main_quit()
    view.connect('load-changed', loaded)
    view.load_html('<title>Browser check</title><p>Local rendering works</p>', 'about:blank')
    GLib.timeout_add_seconds(15, lambda: (Gtk.main_quit(), False)[1])
    Gtk.main()
    assert done, 'WebKit did not finish loading HTML'
    window.destroy()
    print('WebKit rendered local HTML successfully.')
