#!/usr/bin/env python3
"""Process fixtures; --live verifies GTK geometry and disposable child signalling."""
from dataclasses import replace
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/round-desktop'))
from round_processes import Sampler, Process, Snapshot, read_process, filter_processes, can_end, end_process

checks = 0
def check(value, message):
    global checks
    assert value, message
    checks += 1


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'stat').write_text('cpu 100 0 40 860 0 0 0 0 99 0\n')
    (root / 'meminfo').write_text('MemTotal: 1024000 kB\nMemAvailable: 512000 kB\n')
    (root / '42').mkdir()
    fields = ['S'] + ['0'] * 21
    fields[11], fields[12], fields[19], fields[21] = '10', '5', '12345', '100'
    (root / '42/stat').write_text('42 (name ) with spaces) ' + ' '.join(fields))
    (root / '43').mkdir()  # exited/inaccessible entry skipped
    sampler = Sampler(root)
    first = sampler.sample()
    check(first.cpu is None and first.processes[0].cpu is None, 'first sample has no fabricated CPU percentage')
    check(len(first.processes) == 1, 'disappearing processes skipped')
    process = first.processes[0]
    check(process.name == 'name ) with spaces' and process.start == 12345 and process.ticks == 15, 'stat parsing')
    check(process.memory == 100 * os.sysconf('SC_PAGE_SIZE'), 'RSS units')
    check(first.used == 512000 * 1024, 'available memory excludes reclaimable cache')
    (root / 'stat').write_text('cpu 130 0 60 910 0 0 0 0 999 0\n')
    fields[11] = '30'
    (root / '42/stat').write_text('42 (new name) ' + ' '.join(fields))
    with patch('round_processes.time.monotonic', return_value=first.timestamp + 2):
        second = sampler.sample()
    check(second.cpu == 50, 'system CPU ignores double-counted guest time')
    check(math.isclose(second.processes[0].cpu, 100 * 20 / sampler.hz / 2), 'per-process CPU delta')
    fields[19] = '67890'
    (root / '42/stat').write_text('42 (replacement) ' + ' '.join(fields))
    third = sampler.sample()
    check(third.processes[0].cpu is None, 'PID reuse resets CPU baseline')
    check(filter_processes(first.processes, 'WITH') == list(first.processes), 'case insensitive name search')
    check(filter_processes(first.processes, '42') == list(first.processes), 'PID search')
    check(not filter_processes(first.processes, 'no-match'), 'empty search result')

p = Process(9876, 1234, 'test', 'S', os.getuid(), 'user', 0, 1024, 10)
other = replace(p, pid=9877, name='alpha', memory=2048, cpu=2)
check(filter_processes((p, other), sort='cpu')[0] == p, 'CPU sort')
check(filter_processes((p, other), sort='memory')[0] == other, 'memory sort')
check(filter_processes((p, other), sort='name')[0] == other, 'name sort')
for protected in (replace(p, pid=1), replace(p, pid=os.getpid()), replace(p, uid=os.getuid()+1), replace(p, state='Z')):
    check(not can_end(protected), 'protected process')
    try:
        end_process(protected)
    except PermissionError:
        checks += 1
    else:
        raise AssertionError('protected process was signalled')

for name in ('round_tasks.py', 'round_processes.py'):
    compile((ROOT / 'src/round-desktop' / name).read_text(), name, 'exec')
print(f'{checks} backend checks passed.')

if '--live' not in sys.argv:
    sys.exit(0)

# Only children created by this test ever receive real signals.
for force in (False, True):
    child = subprocess.Popen(['sleep', '60'])
    try:
        target = read_process(child.pid)
        try:
            end_process(replace(target, start=target.start+1), force)
        except ProcessLookupError:
            checks += 1
        else:
            raise AssertionError('stale process identity accepted')
        check(child.poll() is None, 'stale identity did not end child')
        end_process(target, force)
        check(child.wait(timeout=3) == -(signal.SIGKILL if force else signal.SIGTERM), 'requested signal received')
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, GLib
from round_tasks import Tasks

# Exercise install, repeat install, baseline preservation and restoration in a
# temporary home. No actual desktop files or compositor are touched here.
import importlib.util
spec = importlib.util.spec_from_file_location('install_tasks', ROOT / 'scripts/install-round-tasks.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
with tempfile.TemporaryDirectory() as directory:
    home = Path(directory)
    state = home / '.local/state/aroundos-round'
    state.mkdir(parents=True)
    config = home / installer.CONFIG
    config.parent.mkdir(parents=True)
    original_xml = '<openbox_config><windowRules><windowRule title="Terminal · AroundOS" serverDecoration="no" /></windowRules></openbox_config>'
    config.write_text(original_xml)
    baseline = state / 'baseline'
    baseline.mkdir()
    (baseline / 'manifest.json').write_text('{"files": {}, "settings": {}}')
    (state / 'original-backup').write_text(str(baseline))
    with patch.object(installer, 'HOME', home), patch.object(installer, 'STATE', state), patch.object(installer, 'reload_compositor'), patch.object(installer.subprocess, 'run'):
        installer.install()
        backup = next(state.glob('before-tasks-*'))
        check('round_tasks.py' in (home / installer.ENTRY).read_text(), 'desktop entry wired')
        check('Terminal · AroundOS' in config.read_text(), 'existing window rule preserved')
        installer.install()
        check(config.read_text().count('Task Manager · AroundOS') == 1, 'repeat install does not duplicate rules')
        import json
        baseline_manifest = json.loads((baseline / 'manifest.json').read_text())
        check(not baseline_manifest['files'][installer.ENTRY], 'baseline remains original on reinstall')
        installer.restore(backup)
        check(not (home / installer.ENTRY).exists() and config.read_text() == original_xml, 'restore exact preferences')

app = Tasks()
app.set_application_id('org.aroundos.TasksCheck')
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
failures = []

def geometry():
    allocation = app.window.get_allocation()
    check((allocation.width, allocation.height) == (1080, 1080), '1080 square client without title bar')
    rectangles = []
    for widget in app.placed:
        if not widget.get_visible():
            continue
        x, y = widget.translate_coordinates(app.window, 0, 0)
        allocation = widget.get_allocation()
        w, h = allocation.width, allocation.height
        check(max(math.hypot(px-540, py-540) for px in (x, x+w) for py in (y, y+h)) <= 515,
              f'outside circular screen: {widget.get_name()} {(x,y,w,h)}')
        if isinstance(widget, (Gtk.Button, Gtk.Entry)):
            for ox, oy, ow, oh in rectangles:
                check(not (x < ox+ow and x+w > ox and y < oy+oh and y+h > oy), 'overlapping controls')
            rectangles.append((x,y,w,h))

def steps():
    yield lambda: app.snapshot is not None and app.snapshot.cpu is not None
    geometry()
    check(app.snapshot.total > 0 and len(app.snapshot.processes) > 10, 'real proc snapshot')
    subprocess.run(['grim', '/tmp/aroundos-tasks-live.png'], check=True)
    app.toggle_pause()
    saved = app.snapshot
    app.received(replace(saved, used=0), None)
    check(app.snapshot == saved, 'paused discards in-flight samples')
    app.set_sort('memory')
    check(app.rows[0][0].process.memory == max(p.memory for p in saved.processes), 'live memory sorting')
    app.change_page(9999)
    check(not app.next.get_sensitive(), 'last page clamps')
    app.change_page(-9999)
    check(not app.previous.get_sensitive(), 'first page clamps')
    app.search.set_text('no-such-process-xyz')
    yield lambda: app.query == 'no-such-process-xyz'
    check(app.empty.get_visible() and not app.rows[0][0].get_visible(), 'empty state')
    geometry()
    app.search.set_text(str(os.getpid()))
    yield lambda: app.query == str(os.getpid())
    check(any(row[0].process and row[0].process.pid == os.getpid() for row in app.rows), 'search finds own process')
    button = next(row[0] for row in app.rows if row[0].process and row[0].process.pid == os.getpid())
    app.row_clicked(button)
    yield lambda: True
    geometry()
    check(not app.end_button.get_sensitive(), 'self termination disabled in UI')
    # Synthetic details never execute a real signal; clicks are mocked below.
    synthetic = replace(p, name='Very long Unicode process — 日本語 process with more text', memory=2**30, cpu=250)
    app.snapshot = replace(saved, processes=(synthetic,))
    app.selected = synthetic
    app.render()
    yield lambda: True
    geometry()
    app.confirm(False)
    yield lambda: True
    geometry()
    check(app.confirm_button.get_visible() and not app.end_button.get_visible(), 'confirmation controls')
    with patch('round_tasks.end_process') as end:
        app.cancel_confirm()
        check(not end.called, 'cancel does not signal')
        app.confirm(True)
        app.perform_end()
        end.assert_called_once_with(synthetic, True)
        checks_before = end.call_count
        app.perform_end()
        check(end.call_count == checks_before, 'double confirmation cannot signal twice')
    app.snapshot = replace(saved, processes=())
    app.render()
    check(not app.end_button.get_sensitive() and 'exited' in app.detail_note.get_text(), 'exited process')
    app.back()
    app.search.set_text('')
    yield lambda: app.query == ''
    app.snapshot = saved
    app.render()
    app.touching = True
    before = app.rows[0][0].process
    app.paused = False
    app.received(replace(saved, processes=()), None)
    check(app.rows[0][0].process == before, 'press freezes displayed row identity')
    app.released()
    yield lambda: not app.deferred
    check(not app.rows[0][0].get_visible(), 'deferred render after release')
    app.received(None, 'test read failure')
    check('Unable' in app.status.get_text(), 'refresh failure visible')
    app.snapshot = saved
    app.render()
    app.refresh()
    yield lambda: not app.busy
    geometry()

sequence = steps()
pending = None
deadline = time.monotonic() + 12
def inspect():
    global pending, deadline
    try:
        if pending is not None and not pending():
            assert time.monotonic() < deadline, 'UI check timed out'
            return True
        pending = next(sequence)
        deadline = time.monotonic() + 12
        return True
    except StopIteration:
        pass
    except Exception as exc:
        import traceback
        traceback.print_exc()
        failures.append(exc)
    app.window.close()
    return False

app.connect('activate', lambda _: GLib.timeout_add(300, inspect))
app.run([])
check(app.timer is None and app.closed, 'close removes sampling timer')
assert not failures, failures
print(f'{checks} checks passed, including live GTK geometry and safe child termination.')
