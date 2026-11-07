#!/usr/bin/env python3
"""Live GTK integration checks on the Pi; uses only a temporary fixture directory."""
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import time
import traceback
import sys
import subprocess

source = Path(__file__).resolve().parents[1] / 'src/round-desktop/round_files.py'
sys.path.insert(0, str(source.parent))
spec = importlib.util.spec_from_file_location('round_files', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Gio, GLib, Gtk = module.Gio, module.GLib, module.Gtk
fixture = tempfile.TemporaryDirectory(prefix='round-files-check-')
root = Path(fixture.name)
(root / 'A empty folder').mkdir()
(root / 'B nested folder').mkdir()
(root / 'B nested folder' / 'Inside.txt').write_text('Fixture only')
for i in range(20):
    p = root / f'Report {i:02d}.txt'
    p.write_text('Fixture only')
    os.utime(p, (1700000000 + i, 1700000000 + i))
long_name = 'Résumé — long filename with spaces and $(touch sentinel) ' + 'example ' * 12 + '.txt'
(root / long_name).write_text('Fixture only')
(root / '.hidden-fixture').write_text('Fixture only')
app = module.RoundFiles(str(root))
app.set_application_id('org.aroundos.RoundFiles.Check')
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
results = []
failed = False

def record(name, condition):
    if not condition:
        raise AssertionError(name)
    results.append(name)

def geometry(name):
    a = app.window.get_allocation()
    record(name + ': full display', (a.width, a.height) == (1080, 1080))
    records = []
    for widget, _ in app.placed:
        if widget in (app.scroller, app.dock_plate) or not widget.get_visible():
            continue
        a = widget.get_allocation()
        x, y = widget.translate_coordinates(app.window, 0, 0)
        radius = max(math.hypot(px - 540, py - 540) for px in (x, x+a.width) for py in (y, y+a.height))
        record(name + ': visible ' + str(widget.get_accessible().get_name()), radius <= 515)
        records.append((widget, x, y, a.width, a.height))
    controls = [r for r in records if isinstance(r[0], Gtk.Button) and r[0].get_sensitive()]
    for i, left in enumerate(controls):
        for right in controls[i + 1:]:
            _, x, y, w, h = left
            _, a, b, c, d = right
            record(name + ': separate touch targets', not (x < a+c and x+w > a and y < b+d and y+h > b))
    if app.options:
        def check_children(widget):
            if isinstance(widget, Gtk.Button):
                a = widget.get_allocation()
                x, y = widget.translate_coordinates(app.window, 0, 0)
                radius = max(math.hypot(px - 540, py - 540) for px in (x, x+a.width) for py in (y, y+a.height))
                record(name + ': dialog button inside circle', radius <= 515)
                record(name + ': full-size menu touch target', a.height >= 80)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    check_children(child)
        check_children(app.options)
    if os.environ.get('ROUND_FILES_CHECK_SCREENSHOTS'):
        directory = Path(os.environ['ROUND_FILES_CHECK_SCREENSHOTS'])
        directory.mkdir(parents=True, exist_ok=True)
        subprocess.run(['grim', str(directory / (name + '.png'))], check=True)

ready = lambda: not app.loading

def steps():
    yield ready
    record('visible entries and hidden filter', len(app.entries) == 23)
    record('folders first', all(i.get_file_type() == Gio.FileType.DIRECTORY for i in app.entries[:2]))
    record("large icon grid is default", app.view_mode == "grid" and len(app.row_widgets) == len(app.entries))
    record('five bottom toolbar controls', [w.get_accessible().get_name() for w in app.dock_buttons] ==
           ['Back', 'Forward', 'Parent folder', 'Switch to list view', 'Close Files'] and
           all(w.translate_coordinates(app.window, 0, 0)[1] > 930 for w in app.dock_buttons))
    geometry('initial')
    adjustment = app.scroller.get_vadjustment()
    adjustment.set_value(160)
    record('grid scrolls', adjustment.get_value() == 160)
    (root / 'Report new.txt').write_text('Watch refresh')
    yield lambda: not app.loading and len(app.entries) == 24
    record('directory watcher preserves scroll', adjustment.get_value() == 160)
    adjustment.set_value(0)
    app.row_widgets[0].emit('clicked')
    yield ready
    record('open empty folder', not app.entries and 'empty' in app.notice.get_text())
    app.back_button.emit('clicked')
    yield ready
    record('back navigation', app.location.get_path() == str(root))
    app.forward_button.emit('clicked')
    yield ready
    record('forward navigation', app.location.get_path().endswith('A empty folder'))
    app.back_button.emit('clicked')
    yield ready
    app.row_widgets[1].emit('clicked')
    yield ready
    record('nested folder', len(app.entries) == 1)
    app.up_button.emit('clicked')
    yield ready
    record('parent navigation', app.location.get_path() == str(root))
    app.view_button.emit('clicked')
    yield None
    record('scrollable list view', app.view_mode == 'list' and len(app.row_widgets) == len(app.entries))
    geometry('list')
    app.view_button.emit('clicked')
    yield None
    record('grid toggle', app.view_mode == 'grid' and len(app.row_widgets) == len(app.entries))
    app.search_button.emit('clicked')
    app.search_entry.set_text('REPORT 01')
    yield lambda: app.query == 'report 01'
    record('case-insensitive current-folder search', len(app.filtered_entries) == 1 and app.filtered_entries[0].get_name() == 'Report 01.txt')
    geometry('search')
    app.search_entry.set_text('no matching fixture')
    yield lambda: app.query == 'no matching fixture'
    record('search empty state', not app.filtered_entries and 'No matching' in app.notice.get_text())
    app.toggle_search(False)
    yield lambda: not app.query
    record('closing search clears filter', len(app.filtered_entries) == 24 and not app.search_entry.get_visible())
    app.path_button.emit('clicked')
    yield None
    geometry('places')
    record('folder shortcuts prevent underlying touches', all(not w.get_sensitive() for w in app.main_controls + app.row_widgets))
    record('folder shortcuts open', app.options is not None and len(app.place_widgets) == 6)
    app.place_widgets[0].emit('clicked')
    yield ready
    record('Home shortcut', app.location.get_path() == str(module.USER_HOME) and not app.options)
    app.navigate(Gio.File.new_for_path(str(root)))
    yield ready
    app.sort_button.emit('clicked')
    yield ready
    files = [i for i in app.entries if i.get_file_type() != Gio.FileType.DIRECTORY]
    dates = [i.get_attribute_uint64('time::modified') for i in files]
    record('recent sort', dates == sorted(dates, reverse=True))
    app.navigate(Gio.File.new_for_path(str(root / 'does-not-exist')))
    yield ready
    record('error state', bool(app.diagnostic) and not app.entries)
    geometry('error')
    app.navigate(Gio.File.new_for_path('/usr/share'))
    app.navigate(Gio.File.new_for_path(str(root / 'B nested folder')))
    yield ready
    record('cancel stale enumeration', app.location.get_path().endswith('B nested folder') and len(app.entries) == 1)
    app.navigate(Gio.File.new_for_path(str(root)))
    yield ready
    match = next(i for i in app.entries if i.get_name() == long_name)
    adjustment.set_value(adjustment.get_upper())
    yield None
    geometry('long filename')
    record('long filename retained', match.get_name() == long_name)
    last_bottom = (app.row_widgets[-1].translate_coordinates(app.window, 0, 0)[1]
                   + app.row_widgets[-1].get_allocated_height())
    plate_top = app.dock_plate.translate_coordinates(app.window, 0, 0)[1]
    record('last row sits just above toolbar', 0 < plate_top - last_bottom <= 24)

sequence = steps()
predicate = None
deadline = time.monotonic() + 15

def advance():
    global predicate, deadline, failed
    try:
        if predicate is not None and not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError('Asynchronous GTK/GIO operation did not settle')
            return True
        predicate = next(sequence)
        deadline = time.monotonic() + 15
        return True
    except StopIteration:
        pass
    except Exception:
        failed = True
        traceback.print_exc()
    print(json.dumps({'passed': not failed, 'checks': len(results), 'last_check': results[-1] if results else None}))
    app.window.close()
    return False

app.connect('activate', lambda _: GLib.timeout_add(250, advance))
GLib.set_prgname('aroundos-round-files-check')
app.run([])
fixture.cleanup()
raise SystemExit(1 if failed else 0)
