# Security

AroundOS is experimental and has no formal support window. Keep Raspberry Pi OS and browser/media libraries updated through their upstream package channels. Use your distribution’s signed packages for BlueZ.

Do not disclose passwords, SSH private keys, Bluetooth link keys, tokens or private logs in issues. For a suspected vulnerability, use GitHub private vulnerability reporting if enabled; otherwise ask the maintainer for a private reporting channel without publishing exploit details or secrets. No dedicated security email or response SLA is currently configured.

Local applications run with the desktop user's permissions. The Browser uses WebKitGTK's engine/sandbox; other desktop and media applications should not be assumed to provide an additional security boundary.
