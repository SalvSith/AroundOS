# Dial

The optional Dial integration opens a locally packaged watch-face app in fullscreen Chromium. It requires separate access to the Dial source and assets. AroundOS distributes the launcher and packaging code.

## Installation

Place an authorized, clean Dial checkout at `local-assets/dial-upstream/`. Run `python3 scripts/package-dial.py` to create the local package. On the Pi, keep the package under `local-assets/dial-package/` in the AroundOS checkout, install Chromium, then run:

```sh
python3 scripts/dial-app.py install
```

The installer verifies the package manifest before registering Dial in **Apps**. It uses a dedicated browser profile and a loopback server while running.

## Controls and removal

Hold the watch face to open the selector, drag to choose a face, then tap **Apply watch face**. Swipe down from the top centre to exit. Escape cancels the selector or exits the watch.

Close Dial and run `python3 scripts/dial-app.py remove` to restore the previous launcher state. The local package and browser profile stay on the device.
