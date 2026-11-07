"""Small native Wayland virtual keyboard/pointer client. No root or uinput daemon."""
import array
import ctypes as C
import ctypes.util
import math
import os
from pathlib import Path
import select
import shlex
import socket
import struct
import time


def uint(*values): return struct.pack('<' + 'I' * len(values), *values)


def string(value):
    data = value.encode() + b'\0'
    return uint(len(data)) + data + b'\0' * (-len(data) % 4)


class Names(C.Structure):
    _fields_ = [(key, C.c_char_p) for key in ['rules', 'model', 'layout', 'variant', 'options']]


class XKB:
    def __init__(self):
        self.lib = C.CDLL(ctypes.util.find_library('xkbcommon') or 'libxkbcommon.so.0')
        signatures = {
            'xkb_context_new': (C.c_void_p, [C.c_int]),
            'xkb_keymap_new_from_names': (C.c_void_p, [C.c_void_p, C.POINTER(Names), C.c_int]),
            'xkb_keymap_get_as_string': (C.c_void_p, [C.c_void_p, C.c_int]),
            'xkb_state_new': (C.c_void_p, [C.c_void_p]),
            'xkb_state_update_key': (C.c_int, [C.c_void_p, C.c_uint, C.c_int]),
            'xkb_state_serialize_mods': (C.c_uint, [C.c_void_p, C.c_int]),
            'xkb_state_serialize_layout': (C.c_uint, [C.c_void_p, C.c_int]),
            'xkb_context_unref': (None, [C.c_void_p]),
            'xkb_keymap_unref': (None, [C.c_void_p]),
            'xkb_state_unref': (None, [C.c_void_p]),
        }
        for name, (restype, args) in signatures.items():
            method = getattr(self.lib, name); method.restype = restype; method.argtypes = args
        config = {}
        try:
            for line in Path('/etc/default/keyboard').read_text().splitlines():
                if line.startswith('XKB') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key] = shlex.split(value)[0] if shlex.split(value) else ''
        except OSError: pass
        names = Names(b'evdev', config.get('XKBMODEL', 'pc105').encode(),
                      config.get('XKBLAYOUT', 'us').encode(), config.get('XKBVARIANT', '').encode(),
                      config.get('XKBOPTIONS', '').encode())
        self.context = self.lib.xkb_context_new(0)
        self.keymap = self.lib.xkb_keymap_new_from_names(self.context, C.byref(names), 0)
        if not self.keymap:
            self.lib.xkb_context_unref(self.context)
            raise RuntimeError('Could not load the desktop keyboard layout')
        self.state = self.lib.xkb_state_new(self.keymap)
        ptr = self.lib.xkb_keymap_get_as_string(self.keymap, 1)
        self.text = C.string_at(ptr) + b'\0'
        libc = C.CDLL(None); libc.free.argtypes = [C.c_void_p]; libc.free(ptr)

    def key(self, code, down):
        self.lib.xkb_state_update_key(self.state, code + 8, int(down))
        return [self.lib.xkb_state_serialize_mods(self.state, kind) for kind in (1, 2, 4)] + [
            self.lib.xkb_state_serialize_layout(self.state, 1 << 7)]

    def close(self):
        self.lib.xkb_state_unref(self.state)
        self.lib.xkb_keymap_unref(self.keymap)
        self.lib.xkb_context_unref(self.context)


class Output:
    def __init__(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(2)
        self.buffer = b''
        self.globals = {}
        self.next_id = 2
        self.keys, self.buttons = set(), set()
        self.remainder = [0.0, 0.0]
        self.xkb = None
        self.closed = False
        runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        try:
            self.socket.connect(str(Path(runtime) / os.environ.get('WAYLAND_DISPLAY', 'wayland-0')))
            self.send(1, 1, uint(2))
            self.roundtrip()
            self.seat = self.bind('wl_seat', 1)
            pointer_manager = self.bind('zwlr_virtual_pointer_manager_v1', 1)
            keyboard_manager = self.bind('zwp_virtual_keyboard_manager_v1', 1)
            self.pointer = self.allocate()
            self.send(pointer_manager, 0, uint(self.seat, self.pointer))
            self.keyboard = self.allocate()
            self.send(keyboard_manager, 0, uint(self.seat, self.keyboard))
            self.xkb = XKB()
            fd = os.memfd_create('navcon-keymap', os.MFD_CLOEXEC)
            try:
                os.write(fd, self.xkb.text)
                self.send(self.keyboard, 0, uint(1, len(self.xkb.text)), fd)
            finally: os.close(fd)
            self.roundtrip()
        except Exception:
            self.socket.close()
            if self.xkb: self.xkb.close()
            raise

    def allocate(self):
        self.next_id += 1
        return self.next_id

    def bind(self, interface, version):
        if interface not in self.globals: raise RuntimeError(f'Desktop does not support {interface}')
        name, supported = self.globals[interface]
        ident = self.allocate()
        self.send(2, 0, uint(name) + string(interface) + uint(min(version, supported), ident))
        return ident

    def send(self, obj, opcode, data=b'', fd=None):
        packet = uint(obj, ((8 + len(data)) << 16) | opcode) + data
        if fd is None: self.socket.sendall(packet)
        else:
            sent = self.socket.sendmsg([packet], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))])
            if sent < len(packet): self.socket.sendall(packet[sent:])

    def read(self, target=None):
        while True:
            if len(self.buffer) < 8:
                data = self.socket.recv(65536)
                if not data: raise ConnectionError('Desktop connection closed')
                self.buffer += data
                if len(self.buffer) < 8: continue
            obj, header = struct.unpack_from('<II', self.buffer)
            size, op = header >> 16, header & 65535
            if size < 8: raise ConnectionError('Invalid Wayland message')
            if len(self.buffer) < size:
                data = self.socket.recv(65536)
                if not data: raise ConnectionError('Desktop connection closed')
                self.buffer += data
                continue
            data, self.buffer = self.buffer[8:size], self.buffer[size:]
            if obj == target: return
            if obj == 1 and op == 0:
                raise ConnectionError('Wayland rejected input: ' + data[12:].split(b'\0')[0].decode(errors='replace'))
            if obj == 2 and op == 0:
                name, length = struct.unpack_from('<II', data)
                interface = data[8:8 + length - 1].decode()
                version = struct.unpack_from('<I', data, 8 + ((length + 3) // 4) * 4)[0]
                self.globals[interface] = (name, version)
            if target is None and not self.buffer: return

    def roundtrip(self):
        target = self.allocate()
        self.send(1, 0, uint(target))
        self.read(target)

    def poll(self):
        while select.select([self.socket], [], [], 0)[0]: self.read()

    @staticmethod
    def timestamp(): return int(time.monotonic() * 1000) & 0xffffffff

    def key(self, code, down):
        if down == (code in self.keys): return
        if down: self.keys.add(code)
        else: self.keys.discard(code)
        modifiers = self.xkb.key(code, down)
        self.send(self.keyboard, 1, uint(self.timestamp(), code, int(down)))
        self.send(self.keyboard, 2, uint(*modifiers))

    def button(self, code, down):
        if down == (code in self.buttons): return
        if down: self.buttons.add(code)
        else: self.buttons.discard(code)
        self.send(self.pointer, 2, uint(self.timestamp(), code, int(down)))
        self.send(self.pointer, 4)

    def move(self, dx, dy):
        values = []
        for i, value in enumerate((dx, dy)):
            value = value * 256 + self.remainder[i]
            whole = math.trunc(value)
            self.remainder[i] = value - whole
            values.append(whole)
        if any(values):
            self.send(self.pointer, 0, struct.pack('<Iii', self.timestamp(), *values))
            self.send(self.pointer, 4)

    def scroll(self, steps):
        self.send(self.pointer, 5, uint(0))  # wheel
        self.send(self.pointer, 7, struct.pack('<IIii', self.timestamp(), 0, steps * 10 * 256, steps))
        self.send(self.pointer, 4)

    def close(self):
        if self.closed: return
        try:
            for key in list(self.keys): self.key(key, False)
            for button in list(self.buttons): self.button(button, False)
            self.send(self.keyboard, 3)
            self.send(self.pointer, 8)
            self.roundtrip()
        except OSError: pass
        finally:
            self.closed = True
            self.socket.close()
            self.xkb.close()
