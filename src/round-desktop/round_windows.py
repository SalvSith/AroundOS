"""Public Wayland foreign-toplevel protocol: home-only dock and app activation."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import time
from urllib.parse import quote

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
MARKER = RUNTIME / 'aroundos-round-dock-hidden'
STATUS = RUNTIME / 'aroundos-round-windows.json'
TASK_ICONS = RUNTIME / 'aroundos-round-task-icons.ini'
APP_ICONS = {
    'aroundos-browser': 'browser', 'aroundos-round-files': 'files',
    'aroundos-terminal': 'terminal', 'aroundos-settings': 'settings',
    'aroundos-videos': 'photos', 'aroundos-photos': 'photos', 'aroundos-editor': 'editor', 'lxtask': 'task-manager',
    'chrome-127.0.0.1__aroundos-dial_-default': 'dial', 'aroundos-dial': 'dial',
    'vlc': 'vlc', 'org.videolan.vlc': 'vlc', 'aroundos-navcon': 'navcon',
    'pishutdown': 'shutdown',
}

def task_icon_map(windows):
    # wf-panel-pi exposes the title on its GTK task button, but keeps the
    # Wayland app ID private. Only publish titles with an unambiguous icon.
    by_title = {}
    for window in windows:
        title = window.get('title')
        if not title:
            continue
        app_id = window.get('app_id', '').casefold()
        icon = APP_ICONS.get(app_id)
        if app_id == 'lxtask' and title != 'Task Manager · AroundOS':
            icon = None  # Classic Task Manager in Utilities shares this app ID.
        by_title.setdefault(title, set()).add(icon)
    lines = ['[icons]']
    for title, icons in sorted(by_title.items()):
        if len(icons) == 1 and None not in icons:
            lines.append(quote(title, safe='') + '=' + next(iter(icons)))
    return '\n'.join(lines) + '\n'

def uint(*values):
    return struct.pack('<' + 'I' * len(values), *values)

def string(value):
    data = value.encode() + b'\0'
    return uint(len(data)) + data + b'\0' * (-len(data) % 4)

def read_string(data):
    length = struct.unpack_from('<I', data)[0]
    return data[4:4+length-1].decode(errors='replace'), 4 + ((length+3)//4)*4

class Windows:
    def __init__(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(3)
        self.socket.connect(str(RUNTIME / os.environ.get('WAYLAND_DISPLAY','wayland-0')))
        self.buffer = b''
        self.globals, self.windows = {}, {}
        self.next_id = 2
        self.send(1,1,uint(2))
        self.roundtrip()
        name,version = self.globals['zwlr_foreign_toplevel_manager_v1']
        self.send(2,0,uint(name)+string('zwlr_foreign_toplevel_manager_v1')+uint(min(version,3),4))
        self.seat = None
        if 'wl_seat' in self.globals:
            name,version = self.globals['wl_seat']
            self.send(2,0,uint(name)+string('wl_seat')+uint(min(version,7),5))
            self.seat = 5
        self.next_id = 5 if self.seat else 4
        self.roundtrip()

    def send(self, obj, op, payload=b''):
        self.socket.sendall(uint(obj,((len(payload)+8)<<16)|op)+payload)

    def read(self, until=None):
        while True:
            if len(self.buffer) < 8:
                data = self.socket.recv(65536)
                if not data: raise ConnectionError('Wayland connection closed')
                self.buffer += data
            if len(self.buffer) < 8: continue
            obj,header = struct.unpack_from('<II',self.buffer)
            size,op = header>>16,header&65535
            while len(self.buffer) < size:
                data = self.socket.recv(65536)
                if not data: raise ConnectionError('Wayland connection closed')
                self.buffer += data
            data,self.buffer = self.buffer[8:size],self.buffer[size:]
            if obj == until: return
            if obj == 1 and op == 0: raise ConnectionError('Wayland protocol error')
            if obj == 2 and op == 0:
                name = struct.unpack_from('<I',data)[0]
                interface,offset = read_string(data[4:])
                self.globals[interface] = name,struct.unpack_from('<I',data,4+offset)[0]
            elif obj == 4 and op == 0:
                self.windows[struct.unpack_from('<I',data)[0]] = {'states':[]}
            elif obj in self.windows:
                if op == 0: self.windows[obj]['title'] = read_string(data)[0]
                if op == 1: self.windows[obj]['app_id'] = read_string(data)[0]
                elif op == 4:
                    length = struct.unpack_from('<I',data)[0]
                    self.windows[obj]['states'] = list(struct.unpack('<'+'I'*(length//4),data[4:4+length]))
                elif op == 6:
                    self.send(obj,7)
                    self.windows.pop(obj,None)
            if until is None and not self.buffer: return

    def roundtrip(self):
        self.next_id += 1
        self.send(1,0,uint(self.next_id))
        self.read(self.next_id)

    def activate(self, app_id):
        found = False
        for obj, window in self.windows.items():
            if window.get('app_id') == app_id:
                self.send(obj,3)
                if self.seat: self.send(obj,4,uint(self.seat))
                found = True
        self.roundtrip()
        return found

    def home(self):
        for obj in self.windows: self.send(obj,2)
        self.roundtrip()

    def close(self):
        self.socket.close()

def activate(app_id):
    connection = None
    try:
        connection = Windows()
        return connection.activate(app_id)
    except (OSError, KeyError, ConnectionError):
        return False
    finally:
        if connection: connection.close()

def show_home():
    connection = Windows()
    try: connection.home()
    finally: connection.close()

def watch():
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    previous = None
    previous_icons = None
    try:
        while running:
            client = None
            try:
                client = Windows()
                while running:
                    visible = any(1 not in item['states'] for item in client.windows.values())
                    windows = [{k:v for k,v in item.items() if k != 'title'}
                               for item in client.windows.values()]
                    state = json.dumps({'dock_hidden':visible, 'windows':windows},sort_keys=True)
                    if state != previous:
                        if visible: MARKER.touch()
                        else: MARKER.unlink(missing_ok=True)
                        temp = STATUS.with_suffix('.tmp')
                        temp.write_text(state)
                        temp.replace(STATUS)
                        previous = state
                    icons = task_icon_map(client.windows.values())
                    if icons != previous_icons:
                        temp = TASK_ICONS.with_suffix('.tmp')
                        temp.write_text(icons)
                        temp.replace(TASK_ICONS)
                        previous_icons = icons
                    if select.select([client.socket],[],[],1)[0]: client.read()
            except (OSError,KeyError,ConnectionError):
                MARKER.unlink(missing_ok=True)
                TASK_ICONS.unlink(missing_ok=True)
                previous_icons = None
                previous = None
                if running: time.sleep(1)
            finally:
                if client: client.close()
    finally:
        MARKER.unlink(missing_ok=True)
        STATUS.unlink(missing_ok=True)
        TASK_ICONS.unlink(missing_ok=True)

if __name__ == '__main__':
    watch()
