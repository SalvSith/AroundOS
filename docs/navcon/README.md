# NavCon

NavCon maps a Sony Navigation Controller to pointer and keyboard actions in the labwc session. It reads Sony USB and Bluetooth HID reports and sends events through the compositor's virtual pointer and keyboard interfaces.

## Install and pair

From the AroundOS checkout, run as the desktop user:

```sh
python3 scripts/navcon-app.py install
python3 scripts/navcon-admin.py navcon-raw-access.py install
```

The first command installs the desktop entry. The second requests administrator approval for a udev rule that grants the input group read access to this controller model's raw reports. It matches the Sony vendor and product IDs.

Connect the controller with a USB data cable. For wireless use, install a distribution-maintained BlueZ package with Sony cable-pairing support. Open **NavCon → Bluetooth setup**. The setup identifies the attached controller and may request administrator approval for its USB name-compatibility rule. Follow the reconnect prompt, then unplug USB and press **PS**. Pairing assigns the host to the controller and can replace an earlier pairing. If the installed BlueZ package lacks the required fixes, use USB or update the distribution package.

## Use

Open NavCon in **Apps**. Its initial profile assigns the stick to pointer movement, L1/L2 to left/right click, Circle to Enter, Cross to Escape, the D-pad to arrow keys and L3 to pointer boost. PS reconnects the controller. Return the stick and buttons to neutral after connecting or editing mappings.

Profiles allow remapping, cursor-speed and dead-zone adjustments, calibration, keyboard shortcuts and changes to login startup. **Pause** releases held inputs. Closing the window keeps input running, and **Quit** releases the controller. Preferences are stored in `~/.config/aroundos-navcon/profiles.json`.

## Verify and remove

```sh
python3 scripts/check-navcon-core.py
python3 scripts/check-navcon-input.py
```

For the live input check, run `python3 scripts/check-navcon-pi.py` inside the graphical Pi session. It creates a test window and sends input events.

To remove the integration and any compatibility rules you installed:

```sh
python3 scripts/navcon-app.py remove
python3 scripts/navcon-admin.py navcon-bluetooth-compat.py remove
python3 scripts/navcon-admin.py navcon-raw-access.py remove
```

Keep pairing records and backups local. A BlueZ pairing backup may contain authentication keys.
