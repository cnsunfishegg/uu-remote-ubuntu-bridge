# Ubuntu 26.04 port notes

## Status

Ubuntu 26.04 is this fork's primary target, but controller support is still
**experimental**. It has passed the source-level, package-level, and
installer-policy audit below; these checks alone do not prove the same live
controller acceptance as the Ubuntu 24.04 baseline. Do not enable unattended
startup until the six end-to-end checks at the end of this document have
passed on the target machine.

## Audited dependency boundary

| Component | Ubuntu 24.04 baseline | Ubuntu 26.04 target | Bridge policy |
| --- | --- | --- | --- |
| GNOME Remote Desktop | GNOME 46 | 50.2 | Keep the same `grdctl rdp` credential and local-relay interface; test the live Wayland session. |
| libei | 1.2.1 | 1.5.0 or newer | Build the reviewed 1.2.1 backport only on 24.04; use the distribution library on 26.04. |
| FreeRDP | Ubuntu package plus pinned Windows runtime | `freerdp3-x11` 3.31 | Keep the existing pinned Windows relay build and verify the native RDP child separately. |
| Wine | WineHQ stable | WineHQ Resolute stable | Use the matching Resolute repository metadata, not a Noble repository workaround. |

GNOME Remote Desktop 50 requires `libei >= 1.3.901`, so loading the old 1.2.1
library through `LD_LIBRARY_PATH` would be an ABI gamble. Ubuntu 26.04's
`libei1` 1.5.0 source contains the same `xclose (keymap_fd)` change used by the
24.04 backport. The installer records one of two persistent modes:

```text
Ubuntu 24.04  -> UURB_LIBEI_MODE=backport -> bridge-local libei 1.2.1 + fix
Ubuntu 26.04  -> UURB_LIBEI_MODE=system   -> Ubuntu libei1 >= 1.5.0
```

The runtime explicitly clears inherited `LD_LIBRARY_PATH` in `system` mode,
and the verifier requires the running GNOME RDP child to map the system
library. The 65536 descriptor limit and the 4096-descriptor restart guard stay
enabled on both releases.

After an in-place upgrade from 24.04, rerun the installer before starting the
bridge. A saved `backport` mode fails closed on a 26.04 host instead of loading
the old library into GNOME 50.

## Safe validation order

Run these from a logged-in GNOME 50 desktop session. Keep unattended mode off
until the ordinary interactive path is stable.

1. Run the source checks before installation:

   ```bash
   python3 -m unittest discover -s tests -v
   bash -n install.sh scripts/*.sh
   ```

2. Install with the normal interactive flow, complete the official UU sign-in,
   and use a new local relay password. The installer refuses a missing or old
   `libei1` instead of falling back to the 24.04 binary.

3. Run `./scripts/verify.sh --quick`. It must report the Ubuntu system libei
   mode, a `65536` descriptor limit, a live GNOME RDP listener, and the
   approved UU binary identities.

4. Exercise one controller at a time: phone on cellular, macOS, and Windows.
   Confirm video, pointer, physical keys, normal phone text, CJK/clipboard
   text, and reconnect behavior before changing timing or keyboard-route
   settings.

5. Run the full verifier after a real remote session. It observes the UU
   server PID and GNOME RDP descriptor growth for the configured stability
   period without logging typed content.

6. Only then opt into `./install.sh --unattended`, reboot locally once, and
   repeat the cellular connection test. This path enables GDM automatic login:
   anyone with physical access can use the desktop after boot.

## Acceptance record

Treat the following as the minimum 26.04 release gate, rather than evidence
that processes merely start:

1. A normal boot makes the host appear online in UU.
2. A phone on cellular reaches the real GNOME desktop.
3. Mouse, keyboard, Chinese input, and clipboard work.
4. A macOS UU controller works.
5. A Windows UU controller works.
6. An unattended reboot returns the host online without local intervention.

Record only release versions, aggregate verifier results, and the chosen
keyboard route. Do not commit account IDs, credentials, device IDs, raw logs,
or typed/clipboard content.
