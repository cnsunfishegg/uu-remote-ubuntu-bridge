# UU Remote on Ubuntu 26.04: bidirectional control plan

## Product goal and boundary

One **UU Remote** launcher on Ubuntu should do both jobs using the user's
official UU account:

1. A Mac or Windows machine running the official client can see and control
   this Ubuntu computer's **actual logged-in desktop**.
2. This Ubuntu computer can see and control a Mac or Windows machine running
   the official client. Opening, hiding, or closing the Ubuntu controller
   window must not take the Ubuntu host offline.

The Windows client runs under **Wine on Ubuntu**, not WSL. The bridge reuses
UU's own login, discovery, transport, and remote-host capabilities. It does
not implement a new UU protocol. Ubuntu 26.04 is the primary release target;
passing on 24.04 or in a fake X server does not establish 26.04 compatibility.

The interaction contract is equally important: one discoverable launcher;
an ordinary movable, resizable, closable Linux window; a visible, correctly
mapped pointer; keyboard only in the focused destination; consistent
minimize/restore; no exposed black capture canvas when the source moves.
Microphone capture and speaker forwarding stay off unless explicitly enabled
and separately tested.

## The two paths today

```text
Mac / Windows official UU client          Ubuntu keyboard and mouse
                 |                                  |
                 v                                  v
        UU host service in Wine            Linux TigerVNC viewer
                 |                                  |
        private screen :N.0                 localhost x11vnc
                 |                                  |
    desktop relay + input broker       Wine UU GUI on screen :N.1
                 |                                  |
                 v                                  v
      logged-in Ubuntu desktop            UU's own connection
                                                    |
                                              Mac / Windows host
```

The host path and the outgoing controller path have different input and
capture contracts. They may share UU's account and Wine prefix, but must not
share a focus owner or make each other's viewer disappear. `:N.0` and
`:N.1` are screens of **one X server**. They do not provide two independent
keyboards, pointer devices, or Wine desktop namespaces.

## Evidence and what it does not prove

Read-only inspection of the running Ubuntu 26.04.1 / Wine 11.0 machine found
the `uu-remote-bridge.service` active, an Xvfb `:20` with
screens 0 and 1, one Openbox on each screen, a view-only host VNC viewer, and
a separate writable controller VNC viewer. The controller's x11vnc captures
the Wine UU window by ID. The repository and installed controller launcher
had the same SHA-256 at inspection time. A live x11vnc query returned
`id:0x1e00027`, `scale:0.936111`, `input:KMBC`, `viewonly:0`,
`always_inject:1`, and `xwarp:1`. The controller Wine window was active on
screen 1 and occupied `1920x1080+0+0`; one contemporaneous pointer query
reported `SCREEN=0`. That is direct evidence that the pointer can reside on
the other screen while the controller window is active. It does **not** prove
which part of a real click fails: x11vnc can move the pointer when it receives
an event.

The present `scripts/test-controller-lifecycle.py` checks geometry, painting,
focus, and mouse/keyboard events on a **fake local application**. The earlier
real Mac check covered visible video and some window transitions. Neither
establishes that a physical click/keystroke travels through Wine and UU to the
correct control on a Mac or Windows host. Current `-ViewOnly=0`,
`-input KMBC`, `-xwarppointer`, and `-always_inject` flags are configuration,
not end-to-end evidence. The upstream x11vnc documentation also warns that
window-ID capture can miss popups and become unstable when the window is
resized, obscured, or iconified. Switching to root capture to include a popup
can reintroduce a black virtual-desktop background during motion.

Therefore the outgoing controller is **not accepted** for a public release
on the basis of the present flags, screenshots, or local fixtures.

## Design rule: one controller session, one state owner

Keep the existing host adapter while isolating the outgoing controller's
responsibilities behind one coordinator. The coordinator owns an immutable
snapshot (generation number) of:

- UU's selected top-level window and its transient dialogs;
- the source screen/root, window bounds, capture mode, painted bounds, and
  mapping into the Linux viewer's viewport;
- the input destination, keyboard focus, and pressed buttons/modifiers;
- the Linux viewer's open, minimized, restoring, and closing state.

Video and input must use the **same snapshot**. On source replacement,
resize, popup selection, or restore, the coordinator advances the generation
and recomputes the transform before accepting another input event. Inputs
with a stale or invalid transform are discarded. On loss of viewer focus,
session switch, or disconnect, pressed buttons and keys are released once.
The host adapter must not activate the controller GUI, and the controller
must never minimize the host relay on the independent-screen profile.

Today x11vnc injects viewer input on its own, outside the shell window
monitor. A new variable in that shell cannot enforce the generation rule.
Gate 1 must establish whether x11vnc can provide a consistent capture/input
mapping across the observed transitions. If it cannot, the controller needs
an input proxy or a local renderer that actually owns both sides of that
mapping. This is the decision point for a scoped implementation change.

The first coordinator boundary is now implemented. The existing monitor is
the only writer of an atomic runtime state containing the current generation,
candidate UU window, actual capture mode/window, geometry, scale, viewer, and
lifecycle. The trace attaches this generation to observed button/key events.
This makes state races measurable; it does not yet intercept or gate x11vnc's
input injection.

The Linux window manager owns the local frame and dragging. The UU client
owns the content and its own remote-session actions. If both titlebars remain
visible, their minimize/maximize behavior must be idempotent and consistent;
no two polling loops may continually move one window to follow the other.
Only after capture and input work should we choose the final visual treatment
of the duplicated controls.

This is a responsibility boundary, **not** a commitment to rewrite the host
service or to replace TigerVNC immediately. A separate Wine prefix, a
different renderer, and direct Wine-on-desktop control remain prototypes
until they demonstrate account continuity, simultaneous host availability,
popup painting, correct input, and recovery on this actual machine. Prior
two-X-server testing with the *same* prefix encountered Wine `BadWindow`;
that arrangement must not be reintroduced as a presumed fix.

## Execution order and gates

### Gate 0: preserve a reproducible baseline

Record exact source and installed hashes, active processes/screens/windows,
UU/Wine/Ubuntu versions, window geometry, and a safe way to restore the
currently working host service. Keep the existing dirty worktree and account
state. Do not restart the only route by which an operator is connected.
Mark the last few VNC flags as provisional; do not stack further flags.

### Gate 1: find the first incorrect boundary

Reproduce one harmless, visible click and one key action on a real Mac and
then on Windows. Observe only event class, time, coordinates, target IDs, and
pressed/released state; do not log typed text or remote screen contents.

```text
physical Ubuntu input
  -> Linux viewer receives button/key
  -> RFB event arrives at localhost x11vnc
  -> event reaches screen :N.1, intended Wine window and coordinates
  -> Wine UU changes the intended local control
  -> UU sends the intended action to the Mac/Windows target
```

At each arrow record *observed / missing / wrong window / wrong coordinates /
stolen focus*. Separately record whether the same key reaches a local Ubuntu
application. A stationary pointer or a keyboard-focus snapshot alone cannot
name the failing arrow. Keep a fixed-size, unscaled source as a **temporary
diagnostic control** and repeat with scaling and popups only after the base
click succeeds. Reproduce with a real Wine window as well as the fake X11
fixture. If the local steps pass but the remote target fails, investigate the
UU-in-Wine client/network path rather than modifying x11vnc geometry.

The implemented first-boundary recorder is:

```bash
uu-remote trace-controller --duration 15
```

It correlates physical-desktop events aimed at the TigerVNC viewer with
events delivered to the private UU Wine window. It stores only event class,
button number, coordinates, target window IDs, and timing in a mode-0600 JSON
file. It intentionally omits key identities, text, window titles, clipboard,
and pixels. Its strongest successful result is
`input_reached_private_uu_window`; the Mac or Windows result still requires a
visible real-device observation. It also records the coordinator generation,
so events spanning a source/capture change can be identified directly.

### Gate 2: repair at the measured boundary

Fix the first failing arrow with the smallest change that preserves the host
path. Add a behavioral regression test for that failure. When independent
polling loops or multiple geometry owners make the invariant impossible,
move controller window selection, capture, coordinate mapping, and focus into
the single coordinator above. Keep an opt-in old controller path until the
new one has equivalent remote behavior. Do not change the Wine account,
delete a prefix, or switch the host's remote-desktop backend to test a GUI fix.

### Gate 3: make window behavior coherent

Test drag frame by frame using a patterned source so black frames are
detectable; ensure dialogs and exit controls remain painted and clickable.
Check native and inner minimize/restore, maximize below the Quickshell panel,
resize and scale, source replacement when entering/leaving a UU session, and
reconnect after a client crash. The physical viewer must not follow the
private source's position. Keyboard focus must stay local after switching to
another Ubuntu application, and return to UU only when the viewer is selected.

If x11vnc's window-ID and shifted-window modes cannot meet these checks,
prototype a renderer with explicit capture and input mapping behind the same
controller interface. Evaluate it on real Wine/UU before migrating; do not
replace the proven host path as part of this prototype.

### Gate 4: bidirectional real-device acceptance before release

| Direction | Required observations |
| --- | --- |
| Mac -> Ubuntu | Real GNOME desktop, pointer, keys/IME or clipboard, reconnect, host online after controller opens/closes |
| Windows -> Ubuntu | Same checks on the Windows official client |
| Ubuntu -> Mac | Real video; pointer move/click/drag/wheel; typing, modifier release and Mac input-method switching; popup, exit, resize, minimize/restore |
| Ubuntu -> Windows | Same visual, pointer, keyboard, lifecycle, and reconnect checks |

During both outgoing checks, confirm that switching focus to an Ubuntu app
does not also type into the remote target. Repeat after a cold restart and
while a second official client sees this Ubuntu host online. Confirm sound
and microphone policy explicitly, with audio capture off by default.
Record failures and any exclusions per direction. Release only after the
real-device matrix passes; isolated Xvfb tests remain necessary regression
checks but cannot substitute for it.

## Sources of truth

- Current implementation: `scripts/uu-remote-console`,
  `scripts/uu-remote-bridge`, `scripts/test-controller-lifecycle.py`.
- Existing host contract: `docs/architecture.md`,
  `docs/ubuntu-26-04-port.md`.
- Previous local observations: `docs/controller-lifecycle-check-2026-09-23.md`.
- External behavior contract: official x11vnc `doc/OPTIONS.md` (`-id`,
  `-sid`, input and pointer options) and TigerVNC `vncviewer/Viewport.cxx`.
