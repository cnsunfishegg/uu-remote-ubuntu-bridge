## Experimental installer bundle for this fork

This is a pre-release of the [public fork](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge), derived from [Lachlan Chen's UU Remote Ubuntu Bridge](https://github.com/lachlanchen/uu-remote-ubuntu-bridge). The original architecture and MIT attribution remain intact. The `.deb` is a **source-only installer bundle**, not a preconfigured UU host and not an official NetEase package.

This replaces `v0.3.0-rc.1`: the local `UU Remote` window could be black because its launcher mirrored an iconified UU shell instead of the live `winhome` device/remote-session window. The launcher now chooses a full-sized managed window and excludes tiny helper windows. We reproduced the black-window selection on the affected host and confirmed that the revised local TigerVNC viewer receives non-black pixels from the active UU window. Keyboard, mouse, and remote-device interaction still require acceptance against a real second device; this is not a blanket compatibility claim.

### Install

On an x86-64 Ubuntu 24.04 desktop (or an Ubuntu 26.04 test host), download the `.deb` below and run:

```bash
sudo apt install ./uu-remote-ubuntu-bridge-installer_0.3.0-rc2-1_amd64.deb
uu-remote-bridge-setup
```

Run the second command from a logged-in GNOME desktop as the regular user, without `sudo`. It still needs network access, Ubuntu/WineHQ dependencies, a verified download of the official UU Windows installer, and your normal UU account login. The `.deb` itself performs none of those operations during `apt install`.

### Scope and limitations

- This release includes the fork's work-in-progress input-routing, silent-audio, TigerVNC, and Ubuntu 26.04 preview changes.
- Ubuntu 26.04 and UU 4.41 are experimental, not broadly validated. The 4.41 manifest is isolated and is **not** the default release.
- No NetEase binaries, Wine prefixes, credentials, account data, or private logs are bundled.
- On Ubuntu, open the bridge-created **UU Remote** desktop entry, not the separate Wine-generated **UU远程** shortcut. The bridge service runs in the background; opening the window is for account/device management and controlling another machine.
- The source snapshot is not a Git checkout; Git-based automatic update and upgrade commands are not supported from this package. Use a source checkout for those workflows.
- Removing the `.deb` does not remove a user's remote-access configuration. Run `uu-remote-bridge-setup --uninstall` as that desktop user first if you intend to remove the bridge.

The package has been structurally extracted and tested, and the repository unit tests pass. It has **not** been accepted as a clean-install, end-to-end remote session across multiple machines. Do not enable unattended startup until you have verified the interactive path on your host.
