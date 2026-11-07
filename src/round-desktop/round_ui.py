"""Shared native visual language; personal Apple assets remain outside source control."""
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf

ASSETS = Path(__file__).resolve().parents[2] / 'local-assets' / 'symbols'
SYMBOLS = {
 'go-previous-symbolic':'chevron.left', 'go-next-symbolic':'chevron.right',
 'go-up-symbolic':'chevron.up', 'pan-down-symbolic':'chevron.down',
 'window-close-symbolic':'xmark', 'view-grid-symbolic':'square.grid.2x2.fill',
 'view-list-symbolic':'list.bullet', 'view-sort-ascending-symbolic':'arrow.up.arrow.down',
 'system-search-symbolic':'magnifyingglass', 'user-home-symbolic':'house',
 'preferences-system-symbolic':'gearshape', 'emblem-system-symbolic':'gearshape',
 'view-more-symbolic':'ellipsis', 'view-refresh-symbolic':'arrow.clockwise',
 'view-reveal-symbolic':'eye', 'object-select-symbolic':'checkmark',
 'folder-download-symbolic':'arrow.down.to.line', 'folder-documents-symbolic':'doc',
 'folder-pictures-symbolic':'photo', 'folder-music-symbolic':'music.note',
 'drive-harddisk-symbolic':'internaldrive', 'view-fullscreen-symbolic':'arrow.up.left.and.arrow.down.right',
 'system-file-manager-symbolic':'folder.fill', 'user-desktop-symbolic':'display',
 'start-here':'square.grid.3x3.fill', 'wifi':'wifi', 'sound':'speaker.wave.2',
 'display':'display', 'appearance':'paintpalette', 'about':'info.circle',
 'network':'network', 'keyboard':'keyboard', 'bluetooth':'switch.2',
 'classic':'rectangle.on.rectangle', 'terminal':'terminal', 'browser':'globe',
}
CACHE = {}
def symbol_pixbuf(name, size=32):
    path = ASSETS / (SYMBOLS.get(name, name) + '.png')
    key = str(path), size
    if not path.exists():
        return None
    if key not in CACHE:
        CACHE[key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
    return CACHE[key]

def icon(name, size=32):
    pixbuf = symbol_pixbuf(name,size)
    result = Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf else Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DIALOG)
    result.set_pixel_size(size)
    return result

MENU_CSS = b'''
#round-files .action-menu, #round-shell .action-menu {
    background: #202023; border: 1px solid #45454b; border-radius: 47px; padding: 6px;
}
#round-files .action-menu button, #round-shell .action-menu button {
    background: transparent; border: 1px solid transparent; border-radius: 40px;
    min-height: 78px; padding: 0 24px; color: #f5f5f7; font: 25px 'Rubik';
}
#round-files .action-menu button:hover, #round-files .action-menu button:focus,
#round-shell .action-menu button:hover, #round-shell .action-menu button:focus {
    background: #30442c; border-color: #a3ed75;
}
'''

SHELL_CSS = b'''
#round-shell {background:#101012;color:#f5f5f7;font-family:'Rubik',sans-serif;}
#round-shell * {transition:none;animation:none;box-shadow:none;text-shadow:none;}
#round-shell button {background:transparent;background-image:none;color:#f5f5f7;border:1px solid transparent;border-radius:22px;padding:0;min-width:0;min-height:0;}
#round-shell button:hover,#round-shell button:focus {background:#29292e;border-color:#55555e;}
#round-shell button:active {background:#30442c;border-color:#a3ed75;}
#round-shell button.round-app-button:hover, #round-shell button.round-app-button:focus,
#round-shell button.round-app-button:active {background:transparent;border-color:transparent;}
#round-shell .round-app-button:hover .round-app-badge, #round-shell .round-app-button:focus .round-app-badge {box-shadow:inset 0 0 0 2px #85858e;}
#round-shell .round-app-button:active .round-app-badge {box-shadow:inset 0 0 0 3px #a3ed75;}
#round-shell .control {background:#242426;border-radius:50%;}
#round-shell .control.text-control {border-radius:24px;}
#round-shell .terminal-prompt button.control {border-radius:14px;}
#round-shell .terminal-prompt button.destructive-action {background:#48282b;color:#ffb1b5;}
#round-shell .terminal-prompt button.destructive-action:hover,
#round-shell .terminal-prompt button.destructive-action:focus {background:#583034;border-color:#a4646a;}
#round-shell button:disabled {opacity:0.35;}
#round-shell .heading {font:600 38px 'Rubik';color:#f5f5f7;}
#round-shell .app-name {font:24px 'Rubik';color:#f5f5f7;}
#round-shell .body {font:25px 'Rubik';color:#f5f5f7;}
#round-shell .secondary {font:20px 'Rubik';color:#a1a1aa;}
#round-shell .section {font:600 19px 'Rubik';color:#92929a;}
#round-shell .group {background:#202023;border-radius:22px;}
#round-shell .setting-row {border-radius:0;min-height:78px;padding:0 18px;}
#round-shell .setting-row:first-child {border-top-left-radius:22px;border-top-right-radius:22px;}
#round-shell .setting-row:last-child {border-bottom-left-radius:22px;border-bottom-right-radius:22px;}
#round-shell button.settings-tile, #round-shell button.settings-tile:hover,
#round-shell button.settings-tile:focus, #round-shell button.settings-tile:active {
    padding:0; border:0; border-radius:30px; background:transparent;
}
#round-shell separator {background:#343438;min-height:1px;margin:0 18px;}
#round-shell entry {background:#242426;color:#f5f5f7;border:1px solid transparent;border-radius:22px;padding:0 22px;font:26px 'Rubik';min-height:0;}
#round-shell entry.launcher-search {border-radius:40px;padding:0 40px;}
#round-shell entry:focus {border-color:#a3ed75;}
#round-shell switch {min-width:78px;min-height:42px;border-radius:24px;background:#45454b;}
#round-shell switch:checked {background:#8adb64;}
#round-shell switch slider {min-width:36px;min-height:36px;border-radius:24px;background:#ffffff;}
#round-shell scale trough {min-height:8px;border-radius:5px;background:#404046;}
#round-shell scale highlight {background:#a3ed75;border-radius:5px;}
#round-shell scale slider {min-height:28px;min-width:28px;background:white;border-radius:16px;}
'''
