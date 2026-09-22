# v0.3.0-rc.4 — repaired clean install for Ubuntu 26.04

RC4 supersedes RC3. RC3's first-time RDP setup referenced an upstream Jenkins
artifact that has since been deleted, so a clean install could stop with HTTP
404. RC4 builds the Windows SDL FreeRDP relay from a fixed source revision and
hash-pinned, versioned SDL/MSYS2 dependencies instead.

This fork primarily targets x86-64 Ubuntu 26.04 GNOME. It is an unofficial
installer bundle derived from [Lachlan Chen's UU Remote Ubuntu Bridge](https://github.com/lachlanchen/uu-remote-ubuntu-bridge),
not a NetEase Linux application. The original MIT attribution is preserved.

## Install and open

Download `uu-remote-ubuntu-bridge-installer_0.3.0-rc4-1_amd64.deb` below.
In the download directory, run:

```bash
sudo apt install ./uu-remote-ubuntu-bridge-installer_0.3.0-rc4-1_amd64.deb
```

Open **UU Remote Setup** from the Ubuntu app menu and leave the terminal window
open. Setup installs dependencies, downloads and hash-checks the official UU
Windows client, builds the bridge, and asks for normal UU account sign-in. Run
setup as your normal desktop user, not with sudo. After setup, the same menu
entry becomes **UU Remote**. The host can continue running in the background.

## Changes since RC3

- Clean RDP setup no longer depends on the deleted FreeRDP Jenkins download.
  FreeRDP 3.31.1-dev0 is built from fixed commit `168925dac`; every downloaded
  dependency and every installed relay runtime file is SHA-256 checked.
- Fresh installs now default to the audited UU Remote `4.39.2.1561` release
  used by the current 26.04 test machine. Rerunning setup preserves any exact
  bundled, audited existing release instead of silently changing versions.
- The controller viewer retains the RC3 fullscreen/resizing, close-and-reopen,
  mouse, keyboard, and default audio-isolation fixes.

## Acceptance evidence and limits

The RC4 release gate includes a from-empty-directory dependency download and
FreeRDP cross-build, checksum verification of the complete Windows runtime, an
actual launch in a new Wine prefix, unit/controller checks, Debian package
content checks, and setup from the extracted final `.deb` in an isolated home
and prefix. The active 26.04 host installation remains on its already tested
UU `4.39.2.1561` manifest and VNC path.

This is still a prerelease, not a claim that every Windows, macOS, phone,
display, input method, or audio configuration has passed two-device testing.
Before relying on it, check remote video, mouse, keyboard, audio isolation,
fullscreen, exit, and reconnect on your own machines. First-time silent audio
remains the default. UU 4.41 is an isolated experiment, not the default.

No NetEase binaries, Wine prefixes, credentials, private logs, or account data
are in the `.deb`. Internet access, Ubuntu/WineHQ dependencies, compilation
time, and official UU sign-in are required during setup. The `.deb` is a fixed
source snapshot, so Git-based automatic updates are unavailable. Removing the
package alone leaves per-user bridge state untouched; run
`uu-remote-bridge-setup --uninstall` as the desktop user first if you also want
to undo the bridge configuration.
