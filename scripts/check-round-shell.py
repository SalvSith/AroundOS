#!/usr/bin/env python3
"""Live layout/behavior checks. Reads real settings, mocks all setting writes."""
import json,math,os,sys,time,traceback,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/round-desktop'))
from round_shell import Shell,Gtk,Gio,GLib,is_utility
from round_windows import Windows
from round_ui import ASSETS,SYMBOLS

checks=[]
failed=False

def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name)

def geometry(app,name):
    size=app.window.get_allocation();check(name+' full frame',(size.width,size.height)==(1080,1080))
    if app.mode=='settings':
        x,_=app.header.translate_coordinates(app.window,0,0)
        check(name+' centered title',2*x+app.header.get_allocated_width()==size.width and app.header.get_xalign()==0.5)
        check(name+' back visibility',app.back.get_visible()==(app.page_name!='overview'))
    active=[]
    for w in app.placed:
        if not w.get_visible():continue
        a=w.get_allocation();x,y=w.translate_coordinates(app.window,0,0)
        radius=max(math.hypot(px-540,py-540) for px in (x,x+a.width) for py in (y,y+a.height))
        check(name+' circular bounds '+str(w.get_accessible().get_name()),radius<=515)
        if isinstance(w,Gtk.Button):active.append((x,y,a.width,a.height))
    for i,(x,y,w,h) in enumerate(active):
        for a,b,c,d in active[i+1:]:check(name+' separate buttons',not(x<a+c and x+w>a and y<b+d and y+h>b))
    if os.environ.get('ROUND_SHELL_CHECK_SCREENSHOTS'):
        target=Path(os.environ['ROUND_SHELL_CHECK_SCREENSHOTS']);target.mkdir(exist_ok=True,parents=True)
        subprocess.run(['grim',str(target/(name+'.png'))],check=True)

def launch_steps(app):
    yield None
    geometry(app,'launchpad')
    check('real app inventory',any(a['name']=='Chrome' for a in app.apps))
    check('custom Files and Settings',app.apps[0]['custom']=='files' and app.apps[1]['custom']=='settings')
    check('no fake empty message',not app.empty.get_visible())
    root=list(app.filtered_apps)
    check('first page grid order',[a.get('grid_key') for a in root[:12]]==
          ['browser','files','terminal','settings','photos','editor','task-manager','dial','vlc','navcon','utilities','shutdown'])
    folder=next(a for a in root if a.get('folder'))
    check('utilities hidden from root',not any(a['name']=='Chrome' for a in root))
    app.open_app(folder);yield None
    check('all installed utilities included',app.filtered_apps==[a for a in app.apps if is_utility(a)])
    geometry(app,'utilities')
    app.next.emit('clicked');yield None
    check('folder paging',app.page==1)
    geometry(app,'utilities-page-two')
    app.close_folder();yield None
    check('folder closes',app.filtered_apps==root and app.folder is None)
    app.search.set_text('CHROMIUM');yield lambda:app.query=='chromium'
    check('app search',len(app.filtered_apps)==1 and app.filtered_apps[0]['name']=='Chrome')
    app.search.set_text('zzzz-no-app');yield lambda:app.query=='zzzz-no-app'
    check('empty search',not app.filtered_apps and app.empty.get_visible())
    app.search.set_text('');yield lambda:not app.query
    check('search reset',app.filtered_apps==root)
    grid_tiles={'Files':'files','Settings':'settings','Terminal':'terminal','Browser':'browser',
                'Dial':'dial','Photos':'photos','NavCon':'navcon','Shutdown':'shutdown',
                'Task Manager':'task-manager','VLC':'vlc'}
    tile_dir=Path(sys.path[0])/'dock-icons'
    if app.round_grid_icons:tile_dir=tile_dir/'round'
    icon_size=116 if app.round_grid_icons else 104
    for name,filename in grid_tiles.items():
        app.search.set_text(name);yield None
        button=next(w for w in app.dynamic if isinstance(w,Gtk.Button) and w.get_accessible().get_name()==name)
        badge=button.get_child().get_children()[0].badge
        image=badge.get_child()
        if app.round_grid_icons:image=image.get_child()
        gicon,_=image.get_gicon()
        tile=tile_dir/(filename+'.png')
        check(name+' uses its grid tile',isinstance(gicon,Gio.FileIcon) and
              gicon.get_file().get_path()==str(tile) and image.get_pixel_size()==icon_size)
        check(name+' centered square allocation',badge.get_allocated_width()==badge.get_allocated_height()==icon_size)
        if app.round_grid_icons:
            style=button.get_style_context()
            for state in (Gtk.StateFlags.PRELIGHT,Gtk.StateFlags.FOCUSED,Gtk.StateFlags.ACTIVE):
                check(name+' round interaction '+str(state),style.get_background_color(state).alpha<0.01)
    app.search.set_text('');yield None
    calls=[]
    import round_shell
    old=round_shell.launch_custom
    round_shell.launch_custom=lambda mode:calls.append(mode)
    app.open_app(app.apps[0]);round_shell.launch_custom=old
    check('Files launch wiring',calls==['files'])
    client=Windows();client.activate('aroundos-shell-check');client.close()
    yield None

def settings_steps(app):
    yield None
    geometry(app,'settings')
    check('six visible Settings tiles',len(app.settings_tiles)==6 and all(
          tile.get_mapped() for tile in app.settings_tiles.values()))
    app.settings_tiles['sound'].clicked();yield lambda:app.volume.get_sensitive()
    geometry(app,'sound')
    check('live audio state',0<=app.volume.get_value()<=100 and '%' in app.volume_label.get_text())
    writes=[]
    def mock(argv,success=None):
        writes.append(argv)
        if success:success(False)
    app.set_command=mock
    current=app.mute.get_active();app.mute.set_active(not current);yield None
    check('mute failure reverts',app.mute.get_active()==current and len(writes)==1)
    check('mute uses native output',writes[0][:3]==['wpctl','set-mute','@DEFAULT_AUDIO_SINK@'])
    level=app.volume.get_value();app.volume.set_value(30 if level!=30 else 31)
    yield lambda:len(writes)==2
    check('volume debounce',writes[-1][:3]==['wpctl','set-volume','@DEFAULT_AUDIO_SINK@'])
    for page in ('display','appearance','about','network','bluetooth'):
        app.back.clicked();yield None
        app.settings_tiles[page].clicked()
        yield (lambda:app.bluetooth_switch.get_sensitive()) if page=='bluetooth' else None
        check(page+' tile navigation',app.page_name==page and app.content.get_mapped()
              and not any(tile.get_mapped() for tile in app.settings_tiles.values()))
        geometry(app,page)
    app.back.clicked();yield None
    check('Back returns to Settings',app.page_name=='overview')
    geometry(app,'settings-return')
    check('leaving sound makes no extra writes',len(writes)==2)

for symbol in set(SYMBOLS.values()):check('SF Symbol '+symbol,(ASSETS/(symbol+'.png')).exists())
for mode,procedure in [('launchpad',launch_steps),('settings',settings_steps)]:
    app=Shell(mode);app.set_application_id('org.aroundos.Check'+mode.title());app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    iterator=procedure(app);pending=None;deadline=time.monotonic()+15
    def tick():
        global pending,deadline,failed
        try:
            if pending is not None and not pending():
                if time.monotonic()>deadline:raise TimeoutError('Asynchronous screen did not settle')
                return True
            pending=next(iterator);deadline=time.monotonic()+15;return True
        except StopIteration:pass
        except Exception:
            failed=True;traceback.print_exc()
        app.window.close();return False
    app.connect('activate',lambda _:GLib.timeout_add(400,tick))
    GLib.set_prgname('aroundos-shell-check')
    app.run([])
    if failed:break
print(json.dumps({'passed':not failed,'checks':len(checks),'last':checks[-1]}))
raise SystemExit(1 if failed else 0)
