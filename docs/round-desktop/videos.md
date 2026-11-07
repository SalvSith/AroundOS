# Videos

Videos uses the same GTK shell, project typography, curved five-button toolbar and
DockHover behavior as Photos. Open local videos from Files or launch Videos from
Apps. Controls provide previous/next file, play/pause, volume, seek and fullscreen.
Space toggles playback; arrows seek ten seconds; F toggles fullscreen; Escape
returns from fullscreen or closes the player. Tap the fullscreen video to return.
Fullscreen preserves aspect ratio inside the physical circle; no picture edges
are hidden beyond the panel. Files are never modified.

## Playback engine and trust

The backend is the upstream [GStreamer playbin](https://gstreamer.freedesktop.org/documentation/playback/playbin.html)
with its [GTK sink](https://gstreamer.freedesktop.org/documentation/gtk/gtksink.html).
This integrates into the existing GTK3/Wayland app without a separate player
window or a custom decoder. Codecs come from Raspberry Pi OS/Debian packages,
including the FFmpeg-backed libav plugin, rather than downloaded codec bundles.
Only local paths are accepted; the app has no streaming, codec downloader or
shell-command construction from media filenames.

This is broad format support, not a promise of every format. MP4, MKV, WebM, MOV,
AVI, MPEG/TS, Ogg video and other common containers depend on their internal
codecs and the installed plugins. DRM-encrypted media is not supported. A damaged
file or unavailable codec produces an in-app error. High-resolution software
playback can exceed Raspberry Pi 4 performance; hardware acceleration is not
guaranteed by this implementation. The GTK sink preserves aspect ratio.

GStreamer has an active [security advisory process](https://gstreamer.freedesktop.org/security/)
and published decoder vulnerabilities; this is not a security audit or a claim
that media parsing is risk-free. Use the official signed APT repositories and
keep the OS and codec libraries updated. Playback runs as the
normal desktop user, not in a separate security sandbox.

## Installation

Run on the Pi as the desktop user:

```sh
sudo apt update
sudo apt install gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-gtk3 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
cd ~/AroundOS
python3 scripts/install-round-videos.py
python3 scripts/check-round-videos.py
```

The targeted installer registers Videos and common video associations, preserving
Photos and VLC. It backs up the desktop entry and mimeapps.list under
`~/.local/state/aroundos-round/before-videos-*`, and records these paths in the
existing desktop baseline backup when present. Reopen Apps after registration.
The general desktop installer does not require video dependencies; use this
explicit installer after installing packages.

For rollback, restore `.config/mimeapps.list` and the previous
`.local/share/applications/aroundos-videos.desktop` from that backup. If the manifest
marks the desktop entry as absent, remove that entry instead. Run
`update-desktop-database ~/.local/share/applications` afterward. No services,
compositor settings, networking settings or system packages are removed.

The live check generates temporary MP4, WebM and MKV clips with FFmpeg and tests
real decode, pause, seek, volume, folder navigation, replacement, end/replay,
fullscreen exit, circular widget bounds, corrupt-file recovery, file integrity
and pipeline/timer teardown. It writes `/tmp/aroundos-videos.png` for visual review.
