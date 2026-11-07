# Build Your AroundOS Computer

V4R2 / Guide 1.2 / 07 November 2026

Waveshare SKU 24369 display enclosure, desk stand and Raspberry Pi 4 mounted to the screen with the supplied spacers and screws.

[Printable illustrated manual](AroundOS%20Assembly%20Manual.pdf)

> CAD-based guide: physical fit, latch engagement, cable clearance and stand stability need a build check. The Pi mounts on the screen with the supplied spacers and screws. Spacer height, cable clearance and cooling require a physical check.

## Parts

| ID | Part | File | Qty |
| --- | --- | --- | --- |
| A | Front Case | `front-case-v4r2.stl` | 1 |
| B | Display Module | `5inch-1080x1080-lcd-sku24369.stp` | 1 |
| C | Holder Plate | `holder-plate-v4r2.stl` | 1 |
| D | Rear Plate | `Rear Plate V4R2.stl` | 1 |
| E | Stand Connector | `desk-mount-connector-v4r2.stl` | 1 |
| F | Desk Base | `Desk Mount Base V4R2.stl` | 1 |

## Equipment

Raspberry Pi 4 Model B; four supplied spacers and matching screws; microSD card; suitable Pi USB-C supply; short micro-HDMI-to-HDMI cable; USB-A-to-USB-C data cable; keyboard; small screwdriver; soft cloth; print cleanup tools. Check cooler and cover clearance.

## 1. Attach the Pi to the Screen

Use the screen's supplied spacers and screws. Work with power disconnected and the screen supported face down on a clean, soft surface.

1. Prepare Raspberry Pi OS 64-bit Desktop on a microSD card and insert it into the Pi. Keep a keyboard or SSH access available for the bench test.
2. Identify the four Pi mounting points on the screen PCB shown on page 4. Use these, not the outer round-plate bosses. Leave the screen factory screws in place.
3. Fit the four supplied spacers to those mounting points. Start them by hand and seat them evenly without forcing the threads.
4. Lower the Pi onto the spacers with its components facing away from the screen. Keep its USB-A and Ethernet bank toward the right and align all four holes.
5. Fit the supplied screws through the Pi into the spacers. Start all four, then tighten gently in a diagonal sequence until the board is secure and flat.

**Check:** All four holes line up, every spacer is seated, and the Pi is held without bending or touching the display electronics.

**Note:** Spacer height and screw length are not specified here; use the supplied matching set. Exploded gaps are enlarged for clarity.

## 2. Wire and Test on the Bench

Connect and test the Pi while it is mounted to the screen, before starting the enclosure. Power connects only to the Raspberry Pi.

1. Connect Pi micro-HDMI port HDMI0 to the screen's standard HDMI input. Use a micro-HDMI-to-HDMI cable or the matching adapter.
2. Connect a Pi USB-A port to the screen's USB-C Touch port with a data-capable cable. HDMI alone does not provide touch.
3. Connect the power supply only to the Pi USB-C power input, after HDMI and USB touch are connected. Leave screen port 4 unused.
4. Boot, confirm an image and test touch at 1080 x 1080, approximately 60 Hz. Shut down and unplug the Pi power supply; keep HDMI and USB touch connected for enclosure assembly.

**Check:** The screen displays the desktop and touch follows your finger before any cover is fitted.

**Note:** Power Supply > Raspberry Pi USB-C. Video > screen HDMI port 3. Touch > screen USB-C port 5 to Pi USB-A.

## 3. Check the Connected Assembly

The Pi is now attached and connected to the screen. Finish these checks before preparing or fitting any enclosure parts.

1. With the Pi power supply unplugged, check both ends of HDMI and USB touch are fully seated. Keep these two leads connected through the case assembly steps.
2. Inspect the gap between the boards. The Pi must sit flat on all four spacers with no loose screws or contact against the display electronics.
3. Arrange the two interconnects around the board edges, clear of GPIO pins. Leave slack for fitting the holder and rear plate without pulling on either socket.
4. Lift the complete unit by supporting the screen rim, not the Pi or cables. Set it aside on a clean, soft surface before cleaning and checking the printed parts.

**Check:** The screen and Pi are attached, HDMI and touch have passed the bench test, and the power supply is unplugged.

**Note:** The CAD views illustrate alignment. Actual spacer height, cooler, cable plugs, enclosure clearance and cooling require a physical check.

## 4. Prepare the Printed Parts

Set the assembled and tested screen/Pi unit aside while preparing the five printed parts. Keep the electronics away from print-cleanup dust.

1. Import the five STL files at 100% scale in millimetres. Centre each part on the build plate and check that it sits on the bed; several supplied files have offset coordinates.
2. The folder's source notes specify support-free printing in the supplied STL orientations. Inspect the slicer preview, particularly clips and bridges; STEP exports need orientation before slicing.
3. Remove brim, strings and loose material. Smooth only printing defects on mating edges; preserve the designed lips, tabs and latch shapes.
4. Dry-fit the stand connector to the base and inspect the case's retaining features. Do not force a tight fit against the glass. Correct the print before installing the screen.

**Check:** All five parts are clean, flat where intended, and free of cracked or obstructed retaining features.

**Note:** No universal material, layer-height or infill profile is supplied. Print shrinkage and tolerances must be checked on your own printer.

## 5. Seat the Connected Unit in the Case

Install the screen with the Pi already mounted and HDMI and USB touch already connected. Keep the Pi power supply unplugged.

1. Place front case A with its front rim supported on a clean, soft surface and its large rear opening facing up.
2. Hold the connected screen/Pi unit by the screen rim. Orient the glass toward the front opening and keep all cable loops clear of the seating edge.
3. Lower the complete unit into the case from the rear. Keep it square so the screen outer edge settles evenly against its internal seating lip.
4. Check the screen is centred and the Pi, cooler and connected plugs clear the shell. Stop if anything binds; lift the unit out and inspect the fit without forcing it.

**Check:** The connected unit sits evenly in the case; the glass, Pi and cables are free from pressure.

**Note:** The exploded spacing is illustrative. This guide does not establish a measured snap-fit clearance or a tested insertion force.

## 6. Fit the Screen Holder

Fit holder plate C around the already mounted Pi and connected leads. The holder retains the screen within the case.

1. Guide holder plate C around the Pi and its connected leads. Align TOP - HDMI PORT and USB PORTS with the screen connectors, then match the holder tabs to the case.
2. Keep the ring clear of the Pi, components and cable plugs. Engage the matching case features evenly by hand; do not use the board or glass as a pressure point.
3. Check the holder is seated and the screen remains located. Confirm HDMI and USB touch are still fully connected and no cable is caught under the ring.
4. Offer up rear plate D and route the Pi power lead through its cable exit. Keep the power supply unplugged and check the cover clears the cooler, plugs and cable bends.

**Check:** The holder retains the screen, both signal leads remain connected, and the Pi power lead exits freely.

**Note:** The printed enclosure uses slide/click features. The separate Pi-to-screen attachment uses the supplied spacers and screws.

## 7. Close the Back and Fit the Stand

Test the stand's two interfaces before loading them with the display. Keep the screen supported while engaging the rear cover.

1. After the Pi is mounted and all leads are clear, align rear plate D with the case. Keep the stand attachment downward and check the Pi, cooler and plugs clear the inside of the cover.
2. Engage the rear cover tabs and turn gently in the moulded CLOSE direction. Use the OPEN marking when removing it. Watch the perimeter so no cable or connector is pinched.
3. Align connector E with the receiving feature in base F and seat the matching tongue/slot connection. Check the connection holds before attaching the display.
4. Support the display and mate the connector's other end with the rear plate mount. Follow the direction allowed by the matching features; do not twist or hammer them together.
5. Place the assembly on a level desk. Support it as you check that the base sits flat, the display is retained and the cable slack does not pull the stand over.

**Check:** The cover is even, both stand joints hold, and the assembly remains stable when you gently use the touchscreen.

**Note:** This guide covers the desk build. Wall anchors, screw selection and wall load ratings have not been specified or verified.

## 8. Connect and Start AroundOS

The Pi is mounted behind the screen. Its USB-C socket receives power; HDMI and USB touch link it to the Waveshare display.

1. Check the Pi is retained on all four spacers. Confirm HDMI and USB touch are connected, the power lead exits freely, and the cooler and vents are unobstructed.
2. Reconnect power and boot Raspberry Pi OS Desktop. Confirm display and touch still work after closing the enclosure.
3. Check that the active display is HDMI-A-1 at 1080 x 1080, approximately 60 Hz, with scale 1. Keep a keyboard or SSH fallback for setup.
4. Follow the repository's Getting started instructions. Run the desktop installer as the normal desktop user inside the active desktop session, then install optional applications as needed.
5. Open the launcher and a few apps. Check touch at several visible positions, cable strain, stand stability and unobstructed Pi ventilation.

**Check:** AroundOS opens on the round display, touch works, and the assembled unit remains stable in normal use.

**Note:** AroundOS is an experimental desktop customization, not a flashable OS image. Fresh-device installation is not yet fully validated.

Run the installer on the Pi from the repository, as the desktop user:

```sh
python3 scripts/round-desktop.py install
```

Read the [repository installation guide](../../README.md#getting-started) first.

## Final Checks

- [ ] Screen sits evenly; glass and electronics are not under pressure.
- [ ] Holder and rear cover are fully engaged with no cracked clips.
- [ ] No cable is caught in a seam or pulled tight against a connector.
- [ ] Both stand joints hold and the base stays flat during touch use.
- [ ] HDMI image and USB touch work after the cover is closed.
- [ ] Pi is secure on four spacers; its cooler and airflow remain clear.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No Picture | Recheck Pi power, Pi boot, HDMI0 and the USB touch cable. Test with the rear cover open. |
| Picture, No Touch | Use the screen Touch socket and a USB data cable. Confirm the Pi detects USB touch. |
| Flicker or Resets | Check the Pi power supply and USB touch cable. Repeat the bench test before closing the cover. Power connects only to the Pi. |
| Screen or Cover Binds | Unplug power. Remove the affected part; inspect scale, print defects, alignment and cable clearance. |
| Desktop Setup Fails | Use the repository Getting started and troubleshooting sections. Check output name, resolution and scale. |

## Sources and Attribution

- [1  Enclosure Design and Original Instructions](https://www.printables.com/model/847901-case-for-round-waveshare-5in-display) - JN-Husch (@JNHusch), Case for round Waveshare 5in Display.
- [2  Screen Connections and Electrical Information](https://www.waveshare.com/wiki/5inch_1080x1080_LCD) - Waveshare, 5inch 1080x1080 LCD wiki; SKU 24369.
- [3  Raspberry Pi 4 Board and Mounting Pattern](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-mechanical-drawing.pdf) - Raspberry Pi official mechanical drawing: 85 x 56 mm; 58 x 49 mm holes.
- [4  AroundOS Installation and Current Limitations](https://github.com/SalvSith/AroundOS) - Repository README and docs/round-desktop/README.md.

Enclosure design and derived enclosure illustrations: JN-Husch, CC BY-NC-SA 4.0. New manual text: CC BY-NC-SA 4.0. See [LICENSE.txt](../LICENSE.txt). Screen model and its derived illustration are credited to Waveshare; no separate redistribution license was supplied. Port identification also follows the supplied Waveshare details-17 photograph. The user confirmed use of the supplied spacers and screws. Pi geometry is simplified; spacer heights and screw lengths are illustrative. The screen STEP was read directly; the EXE was not executed. Source enclosure page was unavailable during this pass; source print/assembly notes came from the attributed folder README and exploded image.

## Rebuilding

`source/content.json` is the editable procedural source. `source/build_manual.py` rebuilds this Markdown file and the PDF using ReportLab, fontTools and the checked-in CAD projections. The builder embeds regular and bold faces from the project font at `src/round-desktop/fonts/Rubik.ttf`. `source/export_cad.py --screen /path/to/5inch-1080x1080-lcd-sku24369.stp` regenerates the projections using cadquery-ocp 8.0.1.1.0. Run `source/hardware_views.py --screen /path/to/screen.stp` after the enclosure exporter to regenerate the Pi and mounting views. Pi details are schematic; the hole pattern is 58 x 49 mm. The screen model itself is not copied into the repository.

SVGs under `illustrations/` are editable vector CAD views. All views are independently positioned/scaled. Do not use the drawing scale as a manufacturing measurement.
