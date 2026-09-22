# v0.3.0-rc.3 — Ubuntu 26.04-first setup (experimental)

This fork targets x86-64 Ubuntu 26.04 GNOME. Ubuntu 24.04 remains supported
as the upstream baseline. This is an unofficial, source-only installer bundle
derived from [Lachlan Chen's UU Remote Ubuntu Bridge](https://github.com/lachlanchen/uu-remote-ubuntu-bridge),
not a NetEase Linux application. The original MIT attribution is preserved.

## Install and open

Download `uu-remote-ubuntu-bridge-installer_0.3.0-rc3-1_amd64.deb` below.
In the download directory, run:

```bash
sudo apt install ./uu-remote-ubuntu-bridge-installer_0.3.0-rc3-1_amd64.deb
```

Open **UU Remote Setup** from the Ubuntu app menu. Leave the terminal window
open while it installs dependencies, downloads the hash-verified official UU
Windows client, builds the bridge, and asks for your normal UU account sign-in.
Setup asks for sudo when needed; do not run setup itself with sudo. After it
finishes, the same app-menu entry becomes **UU Remote**. Use it to manage this
Ubuntu host or control another computer; the host can run in the background.
If the setup icon is missing, run `uu-remote-bridge-setup` from your logged-in
GNOME desktop terminal. The checksum file is for optional download verification.

## Changes since RC2

- The controller viewer follows UU's active session as it resizes or enters
  fullscreen and releases its local lock when closed, so it can be reopened.
- The package now offers a setup launcher in the app menu; after setup it is
  overridden by the single installed UU Remote entry instead of adding a
  second permanent launcher. The quick start is 26.04-first.
- First-time silent audio remains the default: system microphone and speakers
  are not forwarded by this bridge's default configuration.

## Limits

The RC2 asset is not updated and still has the known black controller issue.
This RC3 contains subsequent local fixes and automated controller-window,
packaging, and unit checks. It is **not** a claim that every Windows, macOS,
phone, display, input method, or audio configuration has passed two-device
acceptance. Check remote video, mouse, keyboard, audio isolation, fullscreen,
exit, and reconnect on your own machines before relying on it. Do not enable
unattended startup by default. UU 4.41 is an isolated experiment, not the
default: the bridge remains pinned to the audited UU 4.33 installer.

No NetEase binaries, Wine prefixes, credentials, private logs, or account data
are in the .deb. Internet access, Ubuntu/WineHQ dependencies, and official UU
sign-in are required during setup. The .deb is a fixed snapshot: Git-based
automatic updates do not work. Removing it alone leaves per-user bridge state
untouched; run `uu-remote-bridge-setup --uninstall` as the desktop user before
removing the package if you want to undo the bridge configuration.
