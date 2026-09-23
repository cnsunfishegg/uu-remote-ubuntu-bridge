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

The local viewer has no second titlebar. `_MOTIF_WM_HINTS` uses its own atom
as its property type; CARDINAL was accepted by Openbox but ignored by XFWM.
Live XFWM frame extents were checked as `0, 0, 0, 0`. Minimize maps to the
taskbar. The borderless viewport can be moved with the desktop's Alt-drag
gesture; private titlebar motion is not synchronized to the outer window.
The inner maximize uses the physical desktop's maximized work area, not true
fullscreen: Quickshell's always-on-top panel otherwise covers UU's only
restore/close buttons. An isolated dock/strut fixture checks this explicitly.

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
