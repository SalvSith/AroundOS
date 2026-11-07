#!/usr/bin/env python3
"""Install/restore the per-user AroundOS round desktop. Run on the Pi, as the desktop user."""
import argparse
import configparser
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import aroundos_cursor

HOME = Path.home()
SOURCE = Path(__file__).resolve().parents[1] / "src/round-desktop"
STATE = HOME / ".local/state/aroundos-round"
POINTER = STATE / "original-backup"
THEME = ".local/share/themes/PiXonyx/gtk-3.0/gtk.css"
FILES = [
    ".config/mimeapps.list", ".local/share/applications/aroundos-photos.desktop",
    ".local/share/applications/eom.desktop",
    ".local/share/applications/aroundos-editor.desktop",
    ".local/share/applications/org.xfce.mousepad.desktop",
    ".local/share/applications/org.xfce.mousepad-settings.desktop",
    ".local/share/applications/lxtask.desktop",
    ".local/share/applications/aroundos-classic-task-manager.desktop",
    ".config/labwc/rc.xml", ".config/labwc/themerc-override",
    ".config/labwc/environment",
    ".config/wf-panel-pi/wf-panel-pi.ini", ".config/xsettingsd/xsettingsd.conf",
    ".config/gtk-3.0/settings.ini", ".config/lxterminal/lxterminal.conf",
    ".config/rpcc/config.ini",
    ".config/pcmanfm/default/desktop-items-0.conf",
    ".config/pcmanfm/default/desktop-items-HDMI-A-1.conf",
    ".local/share/backgrounds/aroundos-round.svg", THEME,
    ".local/share/themes/AroundOSRound/gtk-3.0/gtk.css",
    ".local/share/applications/aroundos-files.desktop",
    ".local/share/applications/aroundos-launchpad.desktop",
    ".local/share/applications/aroundos-settings.desktop",
    ".local/share/applications/aroundos-sleep.desktop",
    ".local/share/applications/rpcc.desktop",
    ".config/autostart/aroundos-round-windows.desktop",
    ".config/autostart/aroundos-round-idle.desktop",
    ".config/autostart/squeekboard.desktop",
    ".local/lib/aroundos-round/keyboard-inset.so",
    ".local/lib/aroundos-round/round-surfaces.so",
]
FONT_NAMES = ["Rubik.ttf", "Rubik-Italic.ttf", "OFL.txt"]
FILES += [".local/share/fonts/aroundos-round/" + name for name in FONT_NAMES]
FILES += aroundos_cursor.FILES
SETTINGS = {
    "org.gnome.desktop.interface": {
        "gtk-theme": "'PiXonyx'", "color-scheme": "'prefer-dark'",
        "font-name": "'Rubik 15'", "enable-animations": "false",
        "cursor-theme": repr(aroundos_cursor.THEME), "cursor-size": "24",
    },
    "sm.puri.Squeekboard": {"scale-in-horizontal-screen-orientation": "0.75"},
}


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def write(relative, text):
    path = HOME / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".aroundos-tmp")
    temp.write_text(text)
    temp.replace(path)


def snapshot():
    STATE.mkdir(parents=True, exist_ok=True)
    if POINTER.exists():
        backup = Path(POINTER.read_text().strip())
        manifest = json.loads((backup / "manifest.json").read_text())
    else:
        backup = STATE / datetime.datetime.now().strftime("backup-%Y%m%d-%H%M%S")
        backup.mkdir()
        manifest = {"files": {}, "settings": {}}
    for relative in FILES:
        if relative in manifest["files"]:
            continue
        path = HOME / relative
        manifest["files"][relative] = path.exists()
        if path.exists():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for schema, values in SETTINGS.items():
        saved = manifest["settings"].setdefault(schema, {})
        for key in values:
            if key not in saved:
                saved[key] = run("gsettings", "get", schema, key).stdout.strip()
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
    POINTER.write_text(str(backup))
    return backup


def base(relative, fallback=""):
    original = Path(POINTER.read_text().strip()) / relative
    return original.read_text() if original.exists() else fallback


def ini(relative, changes, fallback=""):
    data = configparser.ConfigParser(interpolation=None, strict=False)
    data.optionxform = str
    data.read_string(base(relative, fallback))
    for section, values in changes.items():
        if not data.has_section(section):
            data.add_section(section)
        for key, value in values.items():
            data.set(section, key, str(value))
    import io
    buf = io.StringIO()
    data.write(buf, space_around_delimiters=False)
    write(relative, buf.getvalue())


def reload_desktop():
    watcher = str(SOURCE / "round_windows.py")
    run("pkill", "-TERM", "-u", str(os.getuid()), "-f", "^/usr/bin/python3 " + re.escape(watcher) + "$", check=False)
    for _ in range(30):
        if run("pgrep", "-f", "^/usr/bin/python3 " + re.escape(watcher) + "$", check=False).returncode:
            break
        time.sleep(0.05)
    if (HOME / ".config/autostart/aroundos-round-windows.desktop").exists():
        with open(STATE / "windows.log", "a") as log:
            subprocess.Popen(["/usr/bin/python3", watcher], stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    else:
        (Path(os.environ["XDG_RUNTIME_DIR"]) / "aroundos-round-dock-hidden").unlink(missing_ok=True)
    idle = str(SOURCE / "round_idle.py")
    run("pkill", "-TERM", "-u", str(os.getuid()), "-f", "^/usr/bin/python3 " + re.escape(idle) + "$", check=False)
    for _ in range(30):
        if run("pgrep", "-f", "^/usr/bin/python3 " + re.escape(idle) + "$", check=False).returncode:
            break
        time.sleep(0.05)
    if (HOME / ".config/autostart/aroundos-round-idle.desktop").exists():
        with open(STATE / "idle.log", "a") as log:
            subprocess.Popen(["/usr/bin/python3", idle], stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    run("fc-cache", "-f", str(HOME / ".local/share/fonts"), check=False)
    run("labwc", "--reconfigure")
    run("pkill", "-HUP", "-x", "xsettingsd", check=False)
    # Replace only the panel's existing supervisor so it gets the current module.
    run("pkill", "-TERM", "-u", str(os.getuid()), "-f", "^/bin/sh /usr/bin/lwrespawn /usr/bin/wf-panel-pi$", check=False)
    run("pkill", "-TERM", "-x", "wf-panel-pi", check=False)
    run("pcmanfm", "--reconfigure")
    # The module changes only native keyboard/notification layer surfaces.
    run("pkill", "-TERM", "-x", "squeekboard", check=False)
    time.sleep(0.3)
    keyboard_env = os.environ.copy()
    keyboard_module = HOME / ".local/lib/aroundos-round/round-surfaces.so"
    if keyboard_module.exists():
        keyboard_env["GTK_MODULES"] = str(keyboard_module)
    else:
        keyboard_env.pop("GTK_MODULES", None)
    with open(STATE / "panel.log", "a") as log:
        subprocess.Popen(["/usr/bin/lwrespawn", "/usr/bin/wf-panel-pi"], env=keyboard_env,
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    keyboard_autostart = HOME / ".config/autostart/squeekboard.desktop"
    if not keyboard_autostart.exists() or "Hidden=true" not in keyboard_autostart.read_text():
        with open(STATE / "keyboard.log", "a") as log:
            subprocess.Popen(["/usr/bin/sbtest"], env=keyboard_env, stdout=log,
                             stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


def restore():
    if not POINTER.exists():
        raise SystemExit("No round-desktop backup is registered.")
    backup = Path(POINTER.read_text().strip())
    manifest = json.loads((backup / "manifest.json").read_text())
    for relative, existed in manifest["files"].items():
        target = HOME / relative
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / relative, target)
        else:
            target.unlink(missing_ok=True)
    # Force existing GTK clients to drop the cached per-user theme override.
    run("gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", "Adwaita")
    for schema, settings in manifest["settings"].items():
        for key, value in settings.items():
            run("gsettings", "set", schema, key, value)
    reload_desktop()
    POINTER.unlink()
    print("Restored original desktop from", backup)


def install():
    if not Path("/usr/bin/labwc").exists():
        raise SystemExit("Run this on the Raspberry Pi, not the development Mac.")
    outputs = run("wlr-randr", "--json").stdout
    display = next((o for o in json.loads(outputs) if o["name"] == "HDMI-A-1"), None)
    current = next((m for m in display.get("modes", []) if m.get("current")), None) if display else None
    if not current or (current["width"], current["height"]) != (1080, 1080) or display.get("scale") != 1:
        raise SystemExit("Expected HDMI-A-1 at 1080×1080 and scale 1; no changes made.")
    for name in FONT_NAMES:
        if not (SOURCE / "fonts" / name).is_file():
            raise SystemExit(f"Missing bundled font asset: {name}; no changes made.")
    backup = snapshot()
    aroundos_cursor.install(SOURCE, HOME)
    for name in FONT_NAMES:
        font = SOURCE / "fonts" / name
        target = HOME / ".local/share/fonts/aroundos-round" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(font, target)
    write(".config/autostart/aroundos-round-windows.desktop", "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Round desktop visibility", "NoDisplay=true",
        f'Exec=/usr/bin/python3 "{SOURCE / "round_windows.py"}"', ""]))
    write(".config/autostart/aroundos-round-idle.desktop", "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Screen inactivity timer", "NoDisplay=true",
        f'Exec=/usr/bin/python3 "{SOURCE / "round_idle.py"}"', ""]))
    for mode, title, icon_name in (("launchpad", "Apps", str(SOURCE / "launchpad-rocket.svg")), ("settings", "Settings", "applications-system")):
        entry = "\n".join(["[Desktop Entry]", "Type=Application", f"Name={title}", f"Icon={icon_name}",
            f'Exec=/usr/bin/python3 "{SOURCE / "round_shell.py"}" {mode}',
            "Terminal=false", "Categories=System;", f"StartupWMClass=aroundos-{mode}", ""])
        write(f".local/share/applications/aroundos-{mode}.desktop", entry)
        if mode == "settings": write(".local/share/applications/rpcc.desktop", entry)
    write(".local/share/applications/aroundos-sleep.desktop", "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Sleep",
        f'Icon={SOURCE / "sleep-moon.svg"}', "NoDisplay=true",
        f'Exec=/usr/bin/python3 "{SOURCE / "round_sleep.py"}"',
        "Terminal=false", ""]))
    module = HOME / ".local/lib/aroundos-round/round-surfaces.so"
    module.parent.mkdir(parents=True, exist_ok=True)
    temporary_module = module.with_suffix(".new.so")
    run("gcc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", "-o", str(temporary_module), str(SOURCE / "surface-insets.c"), "-lm")
    temporary_module.replace(module)
    environment = base(".config/labwc/environment")
    environment = re.sub(r"^GTK_MODULES=.*\n?", "", environment, flags=re.M)
    environment = re.sub(r"^XCURSOR_(THEME|SIZE)=.*\n?", "", environment, flags=re.M)
    environment += f"\nXCURSOR_THEME={aroundos_cursor.THEME}\nXCURSOR_SIZE=24\n"
    write(".config/labwc/environment", environment.rstrip() + f"\nGTK_MODULES={module}\n")
    write(".config/autostart/squeekboard.desktop", "\n".join([
        "[Desktop Entry]", "Name=Squeekboard", "Type=Application", "NoDisplay=true", "Hidden=true",
        f'Exec=/usr/bin/env "GTK_MODULES={module}" /usr/bin/sbtest', ""]))
    files_icon = SOURCE.parents[1] / "local-assets/symbols/folder.fill.blue.png"
    write(".local/share/applications/aroundos-files.desktop", "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Files",
        "Comment=Browse files using the circular display", f"Icon={files_icon if files_icon.exists() else 'system-file-manager'}",
        f'Exec=/usr/bin/python3 "{SOURCE / "round_files.py"}"',
        "Terminal=false", "Categories=System;FileTools;FileManager;",
        "StartupWMClass=aroundos-round-files", ""]))
    write(".local/share/applications/eom.desktop", "[Desktop Entry]\nType=Application\nName=Image Viewer\nHidden=true\n")
    photo_types = ("image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff", "image/webp", "image/svg+xml")
    write(".local/share/applications/aroundos-photos.desktop", "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Photos", "Icon=folder-pictures",
        f'Exec=/usr/bin/python3 "{SOURCE / "round_photos.py"}" %U',
        "Terminal=false", "Categories=Graphics;Viewer;", "StartupWMClass=aroundos-photos",
        "MimeType=" + ";".join(photo_types) + ";", ""]))
    ini(".config/mimeapps.list", {"Default Applications": {mime: "aroundos-photos.desktop;" for mime in photo_types}})
    run("/usr/bin/python3", str(SOURCE.parents[1] / "scripts/install-round-editor.py"))
    run("/usr/bin/python3", str(SOURCE.parents[1] / "scripts/install-round-tasks.py"))
    run("update-desktop-database", str(HOME / ".local/share/applications"), check=False)
    write(THEME, (SOURCE / "gtk.css").read_text())
    write(".local/share/backgrounds/aroundos-round.svg", (SOURCE / "wallpaper.svg").read_text())
    write(".config/wf-panel-pi/wf-panel-pi.ini", (SOURCE / "wf-panel-pi.ini").read_text())
    write(".config/labwc/themerc-override", (SOURCE / "themerc").read_text())

    ET.register_namespace("", "http://openbox.org/3.4/rc")
    root = ET.fromstring(base(".config/labwc/rc.xml"))
    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    # Mouse emulation collapses all finger contacts into one pointer and prevents
    # Photos pinch zoom and Launchpad touch swipes from reaching GTK.
    for touch in root.findall(ns + "touch"):
        if "waveshare" in touch.get("deviceName", "").casefold() or not touch.get("deviceName"):
            touch.set("mouseEmulation", "no")
    def child(parent, tag, text=None, **attrs):
        e = ET.SubElement(parent, ns + tag, attrs)
        if text is not None:
            e.text = text
        return e
    def set_child(parent, name, value):
        for item in list(parent.findall(ns + name)):
            parent.remove(item)
        return child(parent, name, value)
    theme = root.find(ns + "theme")
    if theme is None:
        theme = child(root, "theme")
    set_child(theme, "cornerRadius", "14")
    set_child(theme, "dropShadows", "no")
    for font in theme.findall(ns + "font"):
        if font.get("place") == "MenuItem":
            set_child(font, "name", "Rubik")
        set_child(font, "size", "15")
        set_child(font, "weight", "Normal")
    child(root, "margin", top="0", bottom="0", left="0", right="0", output="HDMI-A-1")
    placement = child(root, "placement")
    child(placement, "policy", "center")
    rules = child(root, "windowRules")
    normal = child(rules, "windowRule", type="normal")
    child(normal, "action", name="Maximize")
    dialog = child(rules, "windowRule", type="dialog")
    child(dialog, "action", name="AutoPlace", policy="center")
    child(rules, "windowRule", identifier="pishutdown", serverDecoration="no")
    child(rules, "windowRule", title="Text Editor * AroundOS", serverDecoration="no")
    files = child(rules, "windowRule", title="Files · AroundOS", serverDecoration="no")
    child(files, "action", name="Maximize")
    for title in ("Apps · AroundOS", "Settings · AroundOS", "Photos · AroundOS", "Videos · AroundOS", "Task Manager · AroundOS"):
        shell = child(rules, "windowRule", title=title, serverDecoration="no")
        child(shell, "action", name="Maximize")
    prompt = child(rules, "windowRule", identifier="gcr-prompter", fixedPosition="yes", ignoreConfigureRequest="yes")
    child(prompt, "action", name="MoveTo", x="150", y="330")

    # Native fullscreen toggle remains available even if an app hides its chrome.
    keyboard = child(root, "keyboard")
    key = child(keyboard, "keybind", key="W-Escape")
    child(key, "action", name="ToggleFullscreen")
    for existing_keyboard in root.findall(ns + "keyboard"):
        for existing_key in list(existing_keyboard.findall(ns + "keybind")):
            if existing_key.get("key", "").casefold() == "print":
                existing_keyboard.remove(existing_key)
    screenshot = child(keyboard, "keybind", key="Print")
    child(screenshot, "action", name="None")
    write('.config/autostart/aroundos-recording.desktop', '[Desktop Entry]\nType=Application\nName=AroundOS Recording\n'
          f'Exec=/usr/bin/python3 "{SOURCE / "round_record.py"}" --daemon\nX-GNOME-Autostart-enabled=true\n')
    ET.indent(root)
    write(".config/labwc/rc.xml", ET.tostring(root, encoding="unicode") + "\n")

    xs = base(".config/xsettingsd/xsettingsd.conf")
    values = {"Net/ThemeName": '"PiXonyx"', "Gtk/FontName": '"Rubik 15"',
              "Gtk/CursorThemeName": f'"{aroundos_cursor.THEME}"', "Gtk/CursorThemeSize": "24",
              "Gtk/EnableAnimations": "0", "Gtk/ColorScheme": '""'}
    for key, value in values.items():
        xs = re.sub(r"^" + re.escape(key) + r" .*\n?", "", xs, flags=re.M)
        xs += f"{key} {value}\n"
    write(".config/xsettingsd/xsettingsd.conf", xs)
    ini(".config/gtk-3.0/settings.ini", {"Settings": {
        "gtk-theme-name": "PiXonyx", "gtk-font-name": "Rubik 15",
        "gtk-cursor-theme-name": aroundos_cursor.THEME, "gtk-cursor-theme-size": "24",
        "gtk-application-prefer-dark-theme": "true", "gtk-enable-animations": "false",
    }})
    ini(".config/lxterminal/lxterminal.conf", {"general": {
        "fontname": "Monospace 14", "bgcolor": "rgb(18,22,24)",
        "fgcolor": "rgb(232,238,235)", "cursorblinks": "false",
        "geometry_columns": "64", "geometry_rows": "24",
    }})
    ini(".config/rpcc/config.ini", {"*": {"width": "700", "height": "480"}})
    desktop = {"*": {
        "wallpaper_mode": "fit", "wallpaper_common": "1",
        "wallpaper": str(HOME / ".local/share/backgrounds/aroundos-round.svg"),
        "desktop_bg": "#101014141616", "desktop_fg": "#e8e8eeeeebeb",
        "desktop_font": "Rubik 15", "show_trash": "0", "show_mounts": "0",
    }}
    for name in ("desktop-items-0.conf", "desktop-items-HDMI-A-1.conf"):
        ini(".config/pcmanfm/default/" + name, desktop,
            Path("/etc/xdg/pcmanfm/default/desktop-items-0.conf").read_text())
    for schema, values in SETTINGS.items():
        for key, value in values.items():
            run("gsettings", "set", schema, key, value)
    reload_desktop()
    print("Round desktop installed; original backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "restore"))
    args = parser.parse_args()
    os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={os.environ['XDG_RUNTIME_DIR']}/bus")
    session_pid = run("pgrep", "-u", str(os.getuid()), "-x", "labwc").stdout.strip()
    if not session_pid.isdigit():
        raise SystemExit("Expected one active labwc session for this user.")
    os.environ["LABWC_PID"] = session_pid
    os.environ.setdefault("DISPLAY", ":0")
    if args.action == "install":
        try:
            install()
        except Exception:
            if POINTER.exists():
                restore()
            raise
    else:
        restore()
