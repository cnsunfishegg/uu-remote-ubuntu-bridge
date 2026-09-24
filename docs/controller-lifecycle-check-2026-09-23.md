# Controller lifecycle regression check (2026-09-23)

Platform: installed Ubuntu 26.04 X11 desktop with Quickshell; approved UU
4.39.2.1561. This is a local validation record, not a release acceptance claim.

## Reproduced before the change

- Clicking UU's inner minimize button iconified the private Wine window,
  leaving a visible black TigerVNC canvas. Reopening the shortcut could restore
  it, but the ordinary minimize/taskbar interaction was broken.
- Clicking UU's inner close button withdrew the management window to its tray.
  Merely mapping that X window did not restore Qt's actual drawing.
- Resizing the local viewer changed the viewport but not its framebuffer scale:
  larger windows retained a small image, and smaller windows cropped it.
- An early implementation of minimize synchronization interfered with session
  exit: Wine briefly iconifies windows during teardown. Immediately remapping
  them could resurrect the session/dialog and minimize the outer app. Stopping
  the monitor allowed the same visible confirmation button to exit normally.

## Changed behavior

- A stable inner minimize minimizes the local viewer and restores the private
  source behind it, allowing taskbar restoration without a blank canvas.
- A short iconic transition is allowed to complete. Returning to a different,
  minimized launcher restores that launcher without minimizing the whole app.
- When all full-size UU surfaces withdraw, the viewer closes and releases its
  lease. Reopening invokes UU's own single-instance activation in the configured
  private Wine environment, preserving its existing audio configuration.
- The framebuffer scales proportionally to the actual local viewport. This
  avoids forcing size changes on UU's fixed-layout launcher. Aspect-ratio
  differences intentionally leave borders rather than stretching the image.

## Validation performed

- Stopped the local controller, UU bridge service, and its Wine processes;
  verified no UU, VNC, or private Xvfb processes remained before cold start.
- Clicked the real inner minimize and close controls; checked both window
  states and screenshots after taskbar restoration and reopening.
- Resized the actual controller larger and smaller; visually verified that
  the settled frame included the entire UI. Changes can briefly show the old
  frame while the monitor and VNC update; this is not zero-latency resizing.
- Connected to a real Mac, observed its full live display, tested outer
  maximization and inner maximize/restore, opened the exit confirmation, and
  confirmed session exit returned to the visible management window.
- Verified the scaled exit button coordinates against the pointer on the
  private source display. No changes to remote documents were part of testing.
- Verified Quickshell retained its normal 46-pixel top panel and that the saved
  audio policy remained `off`. No microphone/audio loopback test was performed.
- `python3 scripts/test-controller-lifecycle.py` runs the actual console with
  Openbox, TigerVNC and fake application windows on two isolated Xvfb displays.
  It checks minimize/taskbar restore, smaller viewport scaling, scaled mouse
  and keyboard forwarding to the fake source, transient
  iconification during session destruction, and inner-close cleanup.

Remote keyboard typing, long-duration connections, Wayland, multiple monitors,
and other remote operating systems are not covered by this live session.

## Follow-up: one set of controls and host/controller isolation

The earlier lifecycle fix did **not** protect incoming host capture. Opening
the local console minimized the physical-desktop relay on the same canvas;
closing/minimizing one surface could therefore affect the other direction.

For the native VNC + direct X11-input profile, the host stays on screen 0 and
the UU GUI now uses screen 1 of the authenticated private X server. RDP and
non-direct-input profiles retain their legacy canvas. Two entirely separate
X servers sharing Wine's default desktop were tested and rejected: Wine tried
to use window IDs on the wrong server and the real UU GUI exited with BadWindow.
That experimental arrangement is not installed or shipped.

Screens still share X input, so canvas separation alone is insufficient:

- The host VNC viewer is view-only with keyboard grabs disabled; incoming
  mouse/keyboard still use the authenticated direct physical-X11 helper.
- Host supervision maps/raises the relay without stealing controller focus.
- Physical VNC cursor positions are not reflected back into the private X
  pointer. The physical cursor is rendered into the host framebuffer instead.
- The local viewer disables pointer-position feedback and uses XWarpPointer
  to target the correct screen, including when the other screen has focus.

An earlier attempt removed the local viewer's titlebar with `_MOTIF_WM_HINTS`.
Although that removed duplicate buttons, private-window motion and physical
viewer motion then fed back through different pointer coordinate systems.
The viewer now retains its native titlebar, which alone owns physical dragging.
At this stage, the private window could move within Xvfb while a root crop
followed it; out-of-bounds source coordinates were clamped, and the crop used
the source client's actual root coordinates rather than `xdotool`'s extra WM
decoration offset. Either set of maximize/restore buttons is mirrored to the
other and uses the physical desktop's work area, not true fullscreen, so an
always-on-top Quickshell panel cannot hide the Linux restore button. Native
and inner minimize both have a taskbar restore path.

Follow-up validation:

- Real inner minimize produced `Iconic` on the local viewer while the host
  relay stayed `Normal`; reopening returned to `Normal`. Real inner close
  removed the local viewer, and reopening restored the painted launcher.
- The isolated lifecycle test now runs **both** VNC directions, checks actual
  decoration extents and precise scaled pointer coordinates, and verifies an
  unobscured physical-desktop patch stays visible through every transition.
- `scripts/test-x11-mouse.sh` passed ordered mouse/wheel and Shift+A/Left
  press/release records through the Wine broker into the X11 helper.
- A live Windows GDI pixel probe agreed with the private host X11 framebuffer.
  This is a local capture check, not a real Mac-to-Linux stream acceptance.
- Unit tests: 171 total, 170 passed, 1 skipped. Audio policy remains off.

The incoming path still needs a real Mac-to-Linux reconnect acceptance test.
Mac Caps Lock/input-method switching was neither modified nor certified.
No release was published from this check.

## Follow-up: native window ownership and crop alignment

The isolated Openbox/TigerVNC/Xvfb lifecycle test now also checks native
titlebar dragging is exactly 1:1, private source movement does not move the
viewer, an escaped source is recovered before first paint, and the viewer's
actual pixels match the source client's top-left region. It exercises both
directions of maximize/restore, native and inner minimize/restore, local versus
remote keyboard focus, scaled pointer input, session disposal, and inner close.
This is local integration evidence, not a two-computer Mac acceptance result.

## Follow-up: eliminate the black intermediate frame

The root crop remained one or more frames behind a moving private UU window.
A 24-move isolated frame comparison exposed the virtual desktop's black
background in 17 intermediate frames, despite correct final alignment. The
local viewer now captures the selected X window directly (`x11vnc -id`), so
window movement does not require a new root crop. An active, overlapping UU
popup temporarily selects `-sid` to include that separate top-level window,
forces a complete framebuffer refresh after the mode switch, then returns to
`-id` when the popup closes. The explicit refresh is required for Wine's
translucent auxiliary windows: without it, x11vnc can retain their initial
opaque black placeholder even though the private X root is correctly painted.
The popup is raised after the mode switch and pointer input is checked through
the viewer. The same 24-move
test passed with zero black intermediate frames using direct capture. This
was also checked against the actual running UU launcher through a view-only
isolated viewer: twenty bounded moves produced zero dark-frame drops, and the
launcher was restored to its original position. A real connected Mac session
still needs acceptance before a release.

For a full-screen remote scene, the sidecar now starts with an exact root clip
instead of changing from `-id` after UU creates its auxiliary windows. The
remote window remains fixed, so there is no drag/crop race; the stable clip
includes the toolbar, control centre, and network overlay in the first
framebuffer and preserves the tested pointer offset.

## Follow-up: explicit controller state and input-boundary trace

The window monitor now publishes one atomic, mode-0600 controller state with a
monotonic generation for source selection, capture mode/window, geometry,
scale, viewer, maximize state, and lifecycle. Cleanup removes the state file.
The isolated lifecycle test verifies that the candidate and actual capture
agree before interaction, then repeats the prior black-frame, popup, scaling,
focus, minimize, and cleanup checks.

`uu-remote trace-controller` independently observes the physical and private
XInput boundaries, counts pointer movement, and attaches the coordinator
generation to button/key events. It does not store key identities, text,
titles, clipboard contents, or pixels. Parser, privacy, boundary diagnosis,
focus-leak diagnosis, and a real isolated XInput collector all passed. A live
preflight found generation 2 in `ready` state with the expected 1920x1080
source and 0.936111 scale. No physical user event occurred during that bounded
capture, so it is not evidence that a click reached the connected Mac.
