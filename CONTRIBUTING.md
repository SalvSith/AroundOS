# Contributing to AroundOS

AroundOS currently targets Raspberry Pi OS Desktop with labwc and the 1080 × 1080 Waveshare round display. Discuss substantial architecture or hardware-support changes in an issue before implementation.

## Development

1. Fork/clone the repository and create a focused branch.
2. Use AroundOS for display names and `aroundos-*` for runtime identifiers.
3. Keep controls inside circular bounds, with usable touch targets and keyboard access.
4. Keep configuration changes reversible and extend backup manifests when adding managed files.
5. Keep unrelated configuration, network and system services intact.
6. Document dependencies, install/restore steps and known limits.

Run `python3 scripts/check-navcon-core.py` and `python3 scripts/check-navcon-input.py` for controller changes. Use the relevant `check-round-*.py` integration checks on the Pi for UI changes; these require real GTK/Wayland dependencies and can open windows or synthesize input. Report which checks ran, where they ran and anything unverified. Do not label historical results as new validation.

Pull requests should explain the problem, resulting behavior, verification and any migration/rollback implications. Use demo accounts and sample data for screenshots. Review visible filenames, terminal prompts, browser tabs and embedded metadata before sharing. Keep generated builds, node_modules, credentials, private fonts, pairing records and local device backups out of Git.

Only contribute material you have permission to redistribute. Identify the source and license of third-party material. Original software contributions use the repository's software license; enclosure derivatives retain CC BY-NC-SA 4.0.
