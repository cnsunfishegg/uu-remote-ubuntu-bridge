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
