"""Build the native AroundOS cursors using the Pi's existing image libraries."""
import struct

THEME = "AroundOSCursor"
ROOT = f".icons/{THEME}"
ALIASES = {
    "desktop_cursor.svg": ("default", "left_ptr", "arrow", "top_left_arrow"),
    "desktop_cursor_hover.svg": (
        "pointer", "hand", "hand1", "hand2", "pointing_hand",
        "e29285e634086352946a0e7090d73106", "9d800788f1b08800ae810202380a0822",
    ),
}
FILES = [f"{ROOT}/index.theme"] + [
    f"{ROOT}/cursors/{name}" for names in ALIASES.values() for name in names
]


def install(source, home):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    from PIL import Image

    target = home / ROOT
    (target / "cursors").mkdir(parents=True, exist_ok=True)
    (target / "index.theme").write_text(
        "[Icon Theme]\nName=AroundOS Cursor\nInherits=PiXtrix,Adwaita\n"
    )
    for asset, names in ALIASES.items():
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(source / "cursors" / asset), 192, 192, True
        )
        image = Image.frombytes(
            "RGBA", (192, 192), bytes(pixbuf.get_pixels()),
            "raw", "RGBA", pixbuf.get_rowstride(), 1,
        ).resize((48, 48), Image.Resampling.LANCZOS)
        # Xcursor stores premultiplied ARGB. The nominal size stays 24 so
        # inherited text/resize cursors retain the desktop's existing size.
        pixels = bytearray()
        for r, g, b, a in image.getdata():
            pixels.extend(struct.pack("<I", (a << 24) |
                ((r * a + 127) // 255 << 16) |
                ((g * a + 127) // 255 << 8) | ((b * a + 127) // 255)))
        data = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
        data += struct.pack("<III", 0xfffd0002, 24, 28)
        data += struct.pack("<9I", 36, 0xfffd0002, 24, 1, 48, 48, 12, 10, 0)
        data += pixels
        for name in names:
            path = target / "cursors" / name
            temporary = path.with_name(name + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
