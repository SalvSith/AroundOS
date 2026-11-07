"""Platform-independent NavCon profiles and held-input engine.

Cursor response follows SalvSith/navcon-toolkit revision e2a7d06.
Linux output uses native held keys; the compositor supplies keyboard repeat.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import time
import uuid

CONTROLS = ['l1', 'l2', 'cross', 'circle', 'l3', 'up', 'down', 'left', 'right', 'ps']
LABELS = dict(zip(CONTROLS, ['L1 · Shoulder', 'L2 · Trigger', 'Cross ×', 'Circle ○',
                           'L3 · Stick click', 'D-pad ↑', 'D-pad ↓', 'D-pad ←', 'D-pad →', 'PS']))
KINDS = {'shortcut': 'Keyboard shortcut', 'modifier': 'Hold modifier',
         'leftClick': 'Left mouse button', 'rightClick': 'Right mouse button',
         'scrollUp': 'Scroll up', 'scrollDown': 'Scroll down',
         'cursorBoost': 'Cursor speed boost (2×)', 'apps': 'Open Apps',
         'pause': 'Pause / resume control', 'none': 'Unassigned'}
MODIFIERS = [29, 42, 56, 125, 97, 54, 100, 126]


def mapping(kind, key=0, mods=(), label=''):
    return {'kind': kind, 'key': key, 'mods': list(mods), 'label': label}


def default_profile():
    return {'id': str(uuid.uuid4()), 'name': 'Everyday', 'speed': 1450.0,
            'deadZone': 0.14, 'centerX': 128.0, 'centerY': 128.0,
            'cursorEnabled': True, 'invertY': False,
            'mappings': {'l1': mapping('leftClick'), 'l2': mapping('rightClick'),
                         'cross': mapping('shortcut', 1, label='Escape'), 'circle': mapping('shortcut', 28, label='Enter'),
                         'l3': mapping('cursorBoost'), 'up': mapping('shortcut', 103, label='↑'),
                         'down': mapping('shortcut', 108, label='↓'), 'left': mapping('shortcut', 105, label='←'),
                         'right': mapping('shortcut', 106, label='→'), 'ps': mapping('none')}}


def sanitize(profile):
    result = default_profile()
    if not isinstance(profile, dict):
        return result
    result['id'] = str(profile.get('id', result['id']))[:80]
    result['name'] = str(profile.get('name', 'Everyday')).strip()[:40] or 'Everyday'
    for key, low, high in [('speed', 100, 2200), ('deadZone', .03, .4), ('centerX', 96, 160), ('centerY', 96, 160)]:
        value = profile.get(key, result[key])
        if isinstance(value, (float, int)) and math.isfinite(value):
            result[key] = max(low, min(high, value))
    for key in ['cursorEnabled', 'invertY']:
        result[key] = bool(profile.get(key, result[key]))
    entries = profile.get('mappings', {})
    for control in CONTROLS:
        value = entries.get(control) if isinstance(entries, dict) else None
        if not isinstance(value, dict) or value.get('kind') not in KINDS:
            continue
        key = value.get('key', 0)
        if not isinstance(key, int) or not 0 <= key <= 255:
            key = 0
        mods = value.get('mods', [])
        if not isinstance(mods, list): mods = []
        result['mappings'][control] = mapping(value['kind'], key,
            [m for m in mods if m in MODIFIERS], str(value.get('label', ''))[:80])
    return result


class Profiles:
    def __init__(self, path):
        self.path = Path(path)
        self.notice = ''
        self.profiles = [default_profile()]
        self.selected = self.profiles[0]['id']
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get('version') not in (1, 2) or not isinstance(data['profiles'], list) or not data['profiles']:
                    raise ValueError('Unsupported profile file')
                self.profiles = [sanitize(p) for p in data['profiles'][:100]]
                self.selected = data.get('selected', self.profiles[0]['id'])
                if not any(p['id'] == self.selected for p in self.profiles): self.selected = self.profiles[0]['id']
                if data['version'] == 1:
                    defaults = default_profile()['mappings']
                    for control in ('cross', 'circle'):
                        self.current['mappings'][control] = defaults[control]
                    self.save()
            except (ValueError, KeyError, TypeError) as exc:
                backup = self.path.with_name(self.path.name + f'.invalid-{time.time_ns()}')
                backup.write_bytes(self.path.read_bytes())
                self.notice = f'Unreadable settings preserved as {backup.name}: {exc}'

    @property
    def current(self):
        return next(p for p in self.profiles if p['id'] == self.selected)

    def save(self):
        self.profiles = [sanitize(p) for p in self.profiles]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'version': 2, 'selected': self.selected, 'profiles': self.profiles}, indent=2) + '\n')
        temp.chmod(0o600)
        temp.replace(self.path)

    def duplicate(self):
        profile = deepcopy(self.current)
        profile['id'] = str(uuid.uuid4())
        profile['name'] = (profile['name'][:35] + ' copy')[:40]
        self.profiles.append(profile)
        self.selected = profile['id']
        self.save()

    def delete(self):
        if len(self.profiles) > 1:
            self.profiles.remove(self.current)
            self.selected = self.profiles[0]['id']
            self.save()


@dataclass
class Report:
    x: float = 128
    y: float = 128
    trigger: float = 0
    buttons: set = field(default_factory=set)


def velocity(report, profile, boosted=False):
    x, y = report.x, report.y
    cx, cy = profile['centerX'], profile['centerY']
    nx = (x - cx) / (255 - cx if x >= cx else cx)
    ny = (y - cy) / (255 - cy if y >= cy else cy)
    radius = math.hypot(nx, ny)
    dead = profile['deadZone']
    if radius <= dead: return 0.0, 0.0
    amount = min(1, (radius - dead) / (1 - dead)) ** 1.45 * profile['speed'] * 1.5 * (2 if boosted else 1)
    return nx / radius * amount, ny / radius * amount * (-1 if profile['invertY'] else 1)


class Engine:
    def __init__(self, output, profile, action=lambda _: None):
        self.output, self.profile, self.action = output, profile, action
        self.enabled = True
        self.editing = False
        self.connected = False
        self.armed = False
        self.report = Report()
        self.previous = set()
        self.held = {}
        self.keys, self.mouse = set(), set()
        self.smooth_x = self.smooth_y = 0.0
        self.scroll_time = 0.0

    @property
    def active(self):
        return self.connected and self.enabled and not self.editing and self.armed

    def reset(self):
        self.held.clear()
        self.sync()
        self.armed = False
        self.smooth_x = self.smooth_y = 0.0

    def connect(self, connected):
        self.reset()
        self.connected = connected
        self.previous = set()
        self.report = Report()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.reset()

    def set_editing(self, editing):
        self.editing = editing
        self.reset()

    def set_profile(self, profile):
        self.reset()
        self.profile = profile

    def receive(self, report):
        pressed = report.buttons - self.previous
        released = self.previous - report.buttons
        self.previous = set(report.buttons)
        self.report = report
        for control in released: self.held.pop(control, None)
        if not report.buttons and velocity(report, self.profile) == (0, 0):
            self.armed = True
        if self.armed and not self.editing:
            if any(self.profile['mappings'][c]['kind'] == 'pause' for c in pressed):
                self.set_enabled(not self.enabled)
                self.action('status')
        if self.active:
            for control in sorted(pressed):
                entry = deepcopy(self.profile['mappings'][control])
                self.held[control] = entry
                if entry['kind'] == 'apps': self.action('apps')
                if entry['kind'] in ('scrollUp', 'scrollDown'):
                    self.output.scroll(-3 if entry['kind'] == 'scrollUp' else 3)
                    self.scroll_time = time.monotonic()
        self.sync()

    def sync(self):
        keys, mouse = set(), set()
        for value in self.held.values():
            if value['kind'] in ('shortcut', 'modifier'):
                keys.update(value['mods'])
                if value['key']: keys.add(value['key'])
            elif value['kind'] == 'leftClick': mouse.add(0x110)
            elif value['kind'] == 'rightClick': mouse.add(0x111)
        # Release regular keys before modifiers; press modifiers before keys.
        for key in sorted(self.keys - keys, key=lambda k: k in MODIFIERS): self.output.key(key, False)
        for key in sorted(keys - self.keys, key=lambda k: k not in MODIFIERS): self.output.key(key, True)
        for button in self.mouse - mouse: self.output.button(button, False)
        for button in mouse - self.mouse: self.output.button(button, True)
        self.keys, self.mouse = keys, mouse

    def tick(self, dt, now):
        if not self.active: return
        if now - self.scroll_time >= .075:
            amount = sum(-2 if m['kind'] == 'scrollUp' else 2 if m['kind'] == 'scrollDown' else 0 for m in self.held.values())
            if amount: self.output.scroll(amount)
            self.scroll_time = now
        if not self.profile['cursorEnabled']:
            self.smooth_x = self.smooth_y = 0
            return
        vx, vy = velocity(self.report, self.profile, any(m['kind'] == 'cursorBoost' for m in self.held.values()))
        if vx == 0 and vy == 0:
            self.smooth_x = self.smooth_y = 0
            return
        dt = max(0, min(.035, dt))
        blend = 1 - math.exp(-dt / .030)
        self.smooth_x += (vx - self.smooth_x) * blend
        self.smooth_y += (vy - self.smooth_y) * blend
        self.output.move(self.smooth_x * dt, self.smooth_y * dt)
