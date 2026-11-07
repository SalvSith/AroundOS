#!/usr/bin/env python3
"""Run Dial as an offline, full-screen Chromium app on the AroundOS desktop."""
import fcntl
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSETS = ROOT / "local-assets/dial-package"
STATE = Path.home() / ".local/state/aroundos-dial"
APP_ID = "chrome-127.0.0.1__aroundos-dial_-Default"


def activate():
    sys.path.insert(0, str(ROOT / "src/round-desktop"))
    from round_windows import activate as activate_window
    return activate_window(APP_ID)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()

    def do_GET(self):
        if not self.allowed_host():
            self.send_error(403)
            return
        path = self.path.split('?', 1)[0]
        if path.startswith('/aroundos-dial/'):
            self.path = self.path[len('/aroundos-dial'):]
            path = self.path.split('?', 1)[0]
        if path == '/favicon.ico':
            self.path = '/DIAL_thumb.png'
        if path in ('/pi-shell.css', '/pi-shell.js'):
            body = (HERE / path[1:]).read_text().replace('__DIAL_TOKEN__', self.server.token).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/css' if path.endswith('.css') else 'text/javascript')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def list_directory(self, _):
        self.send_error(403)
        return None

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (not self.allowed_host() or self.headers.get('Origin', origin) != origin
                or not secrets.compare_digest(self.headers.get('X-Dial-Token', ''), self.server.token)):
            self.send_error(403)
            return
        if self.path == '/app/close':
            self.server.stop.set()
        elif self.path == '/app/activate':
            if not activate():
                self.send_error(503, 'Dial window is still starting')
                return
        else:
            self.send_error(404)
            return
        self.send_response(204)
        self.end_headers()


def main():
    if not (ASSETS / 'manifest.json').is_file():
        raise SystemExit('Dial assets are missing. Run scripts/package-dial.py and deploy the package first.')
    if not shutil.which('chromium'):
        raise SystemExit('Chromium is required; run this launcher on the Raspberry Pi.')
    os.environ.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    os.environ.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS', f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with (STATE / 'app.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Activation may arrive while the first invocation is still starting.
            for _ in range(40):
                try:
                    state = json.loads((STATE / 'running.json').read_text())
                    req = urllib.request.Request(state['url'] + 'app/activate', data=b'',
                                                 headers={'X-Dial-Token': state['token']})
                    with urllib.request.urlopen(req, timeout=2) as response:
                        if response.status == 204:
                            return
                except (OSError, ValueError):
                    time.sleep(0.1)
            raise SystemExit('Dial is already starting; try opening it again in a moment.')
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ASSETS)))
        server.token = secrets.token_urlsafe(32)
        server.stop = threading.Event()
        url = f'http://127.0.0.1:{server.server_port}/'
        (STATE / 'running.json').write_text(json.dumps({'url': url, 'token': server.token, 'pid': os.getpid()}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: server.stop.set())
        args = ['chromium', f'--app={url}aroundos-dial/', '--kiosk', '--ozone-platform=wayland',
                '--class=aroundos-dial', f'--user-data-dir={STATE / "chromium"}',
                '--no-first-run', '--no-default-browser-check', '--disable-session-crashed-bubble',
                '--disable-pinch', '--force-device-scale-factor=1']
        # Diagnostics are opt-in, bound to loopback, and absent in normal launches.
        if os.environ.get('DIAL_DEBUG_PORT'):
            args += ['--remote-debugging-address=127.0.0.1', f"--remote-debugging-port={int(os.environ['DIAL_DEBUG_PORT'])}"]
        browser = None
        try:
            with (STATE / 'chromium.log').open('w') as log:
                browser = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
                while browser.poll() is None and not server.stop.wait(0.25):
                    pass
        finally:
            if browser and browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(browser.pid, signal.SIGTERM)
                    browser.wait(timeout=5)
            server.shutdown()
            server.server_close()
            (STATE / 'running.json').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
