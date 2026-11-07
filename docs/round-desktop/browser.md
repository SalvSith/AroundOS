# Browser

Browser uses the native GTK styling
and a five-control curved bottom dock. The page viewport is 900 × 820
at (90, 260), continuing to the bottom of the 1080 px display behind the floating
toolbar. The circular panel masks the lower corners; scrolling brings content
back into the wider middle. Browser controls retain radius 515 clearance.

The browser samples the visible side backgrounds, including nested application
wrappers, and extends their dominant colour across the native surrounding surface.
An isolated JavaScript world reads computed styles once per second; canvas colour
conversion supports modern CSS colour formats. Transparent root/body backgrounds
follow browser canvas propagation rules. No website layout or styles are changed.
Navigation generations reject stale reads and closing removes the timer.
Background images, gradients and differently coloured sections cannot all be
matched by one surrounding colour; these retain their artwork inside the viewport.
The progress track disappears when idle.

The address field accepts web addresses, localhost URLs and DuckDuckGo searches.
The toolbar provides back, forward, reload/stop, home and close. Ctrl+L focuses
the address, Ctrl+R/F5 reloads, Escape stops, and Ctrl++/−/0 adjusts page zoom.
The existing system touch-keyboard setting is preserved; text entry requires the
user's existing keyboard/input setup. Cookies and website storage persist in
`~/.local/share/aroundos-browser`, with cache in `~/.cache/aroundos-browser`.

WebKitGTK 4.1 supplies the rendering engine and sandbox. TLS checks remain enabled.
Explicit popup links open in the same view; automatic popups are blocked. This
initial version has one page, no download manager and denies site permission
requests (camera, microphone, location, etc.). Downloads show an unsupported notice.
It does not share Chromium's profile, extensions or saved logins. Chromium remains
installed. WebKit dependencies should be kept updated through the OS package manager.

## Setup on the Pi

Install the WebKitGTK 4.1 bindings from the distribution packages:

```sh
sudo apt install gir1.2-webkit2-4.1
```

From a terminal in the active desktop session:

```sh
cd ~/AroundOS
python3 scripts/check-round-browser.py --live
python3 scripts/install-round-browser.py
python3 src/round-desktop/round_browser.py
```

The focused installer snapshots MIME defaults, the Browser desktop entry and panel
configuration under `~/.local/state/aroundos-round/before-browser-TIMESTAMP`. It adds
Browser to Apps, sets HTTP/HTTPS defaults and replaces only the existing browser
shortcut in the live panel configuration. The dock changes on the next panel start.
It does not rerun the full desktop installer or overwrite newer Terminal changes.
Running the older full desktop installer later can reset the dock shortcut; rerun
this focused installer afterward if needed.

Restore the focused changes with:

```sh
python3 scripts/install-round-browser.py restore /path/to/before-browser-TIMESTAMP
```

Source, browser profile and OS packages are retained by restore.

The live check exercises navigation, HTML rendering and circular widget bounds. Use the distribution package manager to keep the engine updated.
