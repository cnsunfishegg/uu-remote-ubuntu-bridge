#!/usr/bin/env python3
"""Run the real console against two isolated X displays, never the user's UU.

Exercises minimize/restore, transient iconification during session disposal,
viewport scaling, and inner-close cleanup using real Openbox and TigerVNC.
"""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from PIL import ImageGrab


REPO = Path(__file__).resolve().parents[1]


def wait_for(description, predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(description)


def run(env, *args):
    return subprocess.run(args, env=env, capture_output=True, text=True,
                          timeout=5).stdout.strip()


def main():
    children = []
    with tempfile.TemporaryDirectory(prefix="uu-lifecycle-") as temp:
        root = Path(temp)
        runtime = root / "runtime"
        private = runtime / "uu-remote-bridge"
        private.mkdir(parents=True)
        (private / "Xauthority").touch()
        base = {**os.environ, "HOME": temp, "XDG_RUNTIME_DIR": str(runtime),
                "XDG_STATE_HOME": str(root / "state"), "XAUTHORITY": str(private / "Xauthority")}
        with (root / "process.log").open("wb") as log:
            def start(args, env=base, **options):
                process = subprocess.Popen(args, env=env, stdout=log, stderr=log, **options)
                children.append(process)
                return process

            def display(two_screens=False):
                process = subprocess.Popen(
                    ["Xvfb", "-displayfd", "1", "-screen", "0", "1600x1000x24",
                     *(["-screen", "1", "1600x1000x24", "-xinerama"] if two_screens else []),
                     "-nolisten", "tcp"],
                    env=base, stdout=subprocess.PIPE, stderr=log)
                children.append(process)
                number = process.stdout.readline().decode().strip()
                assert number.isdigit(), "isolated Xvfb failed"
                env = {**base, "DISPLAY": ":" + number}
                start(["openbox"], env)
                wait_for("window manager did not start", lambda: "WINDOW" in run(
                    env, "xprop", "-root", "_NET_SUPPORTING_WM_CHECK"))
                return env

            def app(env, name, geometry):
                process = start(["xev", "-name", name, "-geometry", geometry], env)
                window = wait_for("test surface missing", lambda: run(
                    env, "xdotool", "search", "--name", "^" + name + "$"))
                run(env, "xdotool", "set_window", "--class", "gameviewer.exe", window)
                return process, window.splitlines()[-1]

            def state(env, window):
                return run(env, "xprop", "-id", window, "WM_STATE")

            try:
                host = display(two_screens=True)
                source = {**host, "DISPLAY": host["DISPLAY"] + ".1"}
                start(["openbox"], source)
                wait_for("controller WM missing", lambda: "WINDOW" in run(
                    source, "xprop", "-root", "_NET_SUPPORTING_WM_CHECK"))
                desktop = display()
                panel = start(["xmessage", "-name", "Test top panel", "-geometry", "1600x50+0+0", "Panel"], desktop)
                panel_id = wait_for("panel fixture missing", lambda: run(
                    desktop, "xdotool", "search", "--onlyvisible", "--name", "^Test top panel$"))
                run(desktop, "xprop", "-id", panel_id, "-f", "_NET_WM_WINDOW_TYPE", "32a",
                    "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK")
                run(desktop, "xprop", "-id", panel_id, "-f", "_NET_WM_STRUT_PARTIAL", "32c",
                    "-set", "_NET_WM_STRUT_PARTIAL", "0, 0, 50, 0, 0, 0, 0, 0, 0, 1599, 0, 0")
                (private / "private-display").write_text(host["DISPLAY"] + "\n")
                (private / "controller-display").write_text(source["DISPLAY"] + "\n")
                run(desktop, "xsetroot", "-solid", "#183e68")
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    host_port = reservation.getsockname()[1]
                start(["x11vnc", "-display", desktop["DISPLAY"], "-localhost", "-no6", "-nopw",
                       "-forever", "-shared", "-nocursorpos", "-nocursorshape", "-rfbport", str(host_port)], desktop)
                def host_listening():
                    try:
                        with socket.create_connection(("127.0.0.1", host_port), timeout=0.1):
                            return True
                    except OSError:
                        return False
                wait_for("host VNC did not start", host_listening)
                relay = start(["vncviewer", "-FullScreen=1", "-ViewOnly=1", "-FullscreenSystemKeys=0",
                               "-Shared=1", "-SecurityTypes=None", f"127.0.0.1::{host_port}"], host)
                relay_id = wait_for("host fixture missing", lambda: run(
                    host, "xdotool", "search", "--onlyvisible", "--name", " - TigerVNC$"))
                time.sleep(0.5)
                # Compare an unobscured physical-desktop patch, not the
                # local controller which legitimately appears in the relay.
                def host_content():
                    return ImageGrab.grab(xdisplay=host["DISPLAY"]).crop((1450, 800, 1550, 900)).tobytes()
                host_pixels = ImageGrab.grab(xdisplay=desktop["DISPLAY"]).crop((1450, 800, 1550, 900)).tobytes()
                wait_for("host did not paint physical desktop", lambda: host_content() == host_pixels)

                def host_unchanged():
                    assert "Normal" in state(host, relay_id), "controller minimized the host relay"
                    assert not (private / "console-focus").exists(), "controller took host focus lease"
                    assert host_content() == host_pixels, "controller overwrote host canvas"

                launcher, launcher_id = app(source, "Lifecycle launcher", "600x450+80+60")
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    port = reservation.getsockname()[1]
                desktop["UURB_CONSOLE_VNC_PORT"] = str(port - 1)
                console = start([str(REPO / "scripts/uu-remote-console"), "window"], desktop)
                viewer = wait_for("viewer did not open", lambda: run(
                    desktop, "xdotool", "search", "--name", "^UU Remote - TigerVNC$"))
                wait_for("launcher not mapped", lambda: "Normal" in state(source, launcher_id))
                wait_for("outer decoration was not removed", lambda: "2, 0, 0, 0, 0" in run(
                    desktop, "xprop", "-id", viewer, "-f", "_MOTIF_WM_HINTS", "32c", "_MOTIF_WM_HINTS"))
                wait_for("WM still shows a second titlebar", lambda: "= 0, 0, 0, 0" in run(
                    desktop, "xprop", "-id", viewer, "_NET_FRAME_EXTENTS"))
                print("PASS only the inner UU window controls remain", flush=True)
                host_unchanged()
                time.sleep(0.6)  # Establish the initial source in the real monitor.

                run(source, "xdotool", "windowminimize", launcher_id)
                wait_for("inner minimize did not minimize viewer", lambda: "Iconic" in state(desktop, viewer))
                wait_for("source not restored for taskbar reuse", lambda: "Normal" in state(source, launcher_id))
                run(desktop, "xdotool", "windowmap", viewer, "windowactivate", viewer)
                wait_for("taskbar restore failed", lambda: "Normal" in state(desktop, viewer))
                time.sleep(1)  # Openbox and TigerVNC complete their restore configure events.
                print("PASS inner minimize and taskbar restore", flush=True)
                host_unchanged()

                run(desktop, "xdotool", "windowsize", viewer, "420", "330")
                channel = f"UURB_WINDOW_{os.getuid()}_{port}_{console.pid}"
                # Remote commands share one X property. Polling -Q rapidly
                # can overwrite the monitor's pending -R scale request.
                time.sleep(2)
                answer = run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel, "-Q", "scale")
                assert "ans=scale:0.700000" in answer, (
                    "viewport scaling was not applied: " + answer + " / " +
                    run(desktop, "xdotool", "getwindowgeometry", "--shell", viewer))
                print("PASS smaller viewport scales the complete source", flush=True)
                events_before = (root / "process.log").read_text(errors="replace")
                run(desktop, "xdotool", "mousemove", "--window", viewer,
                    "210", "165", "click", "1", "key", "a")
                def input_arrived():
                    events = (root / "process.log").read_text(errors="replace")
                    return all(events.count(event) > events_before.count(event)
                               for event in ("ButtonPress event", "KeyPress event"))
                wait_for("scaled viewer did not forward mouse and keyboard", input_arrived)
                pointer = dict(line.split("=", 1) for line in run(source, "xdotool", "getmouselocation", "--shell").splitlines())
                geometry = dict(line.split("=", 1) for line in run(source, "xdotool", "getwindowgeometry", "--shell", launcher_id).splitlines())
                # Test the viewport center; TigerVNC centers the 420x315
                # framebuffer within the taller 420x330 viewport.
                assert abs(int(pointer["X"]) - int(geometry["X"]) - 300) <= 2, (pointer, geometry)
                assert abs(int(pointer["Y"]) - int(geometry["Y"]) - 225) <= 2, (pointer, geometry)
                print("PASS scaled mouse and keyboard reach source", flush=True)

                run(source, "wmctrl", "-ir", hex(int(launcher_id)), "-b", "add,maximized_vert,maximized_horz")
                wait_for("inner maximize did not maximize local viewer", lambda: "MAXIMIZED_VERT" in run(
                    desktop, "xprop", "-id", viewer, "_NET_WM_STATE"))
                maximized_state = run(desktop, "xprop", "-id", viewer, "_NET_WM_STATE")
                assert "FULLSCREEN" not in maximized_state, maximized_state
                viewer_geometry = dict(line.split("=", 1) for line in run(
                    desktop, "xdotool", "getwindowgeometry", "--shell", viewer).splitlines())
                assert int(viewer_geometry["Y"]) >= 50, viewer_geometry
                run(source, "wmctrl", "-ir", hex(int(launcher_id)), "-b", "remove,maximized_vert,maximized_horz")
                wait_for("inner restore left viewer maximized", lambda: "MAXIMIZED_VERT" not in run(
                    desktop, "xprop", "-id", viewer, "_NET_WM_STATE"))
                print("PASS maximize/restore keeps controls below the top panel", flush=True)

                session, session_id = app(source, "Lifecycle session", "900x650+0+0")
                run(source, "xdotool", "windowminimize", launcher_id)
                time.sleep(1)
                # Match Wine's close transition: session briefly Iconic,
                # then destroyed; launcher may still be Iconic during return.
                run(source, "xdotool", "windowminimize", session_id)
                time.sleep(0.12)
                session.terminate()
                session.wait(timeout=3)
                wait_for("launcher not restored after session exit", lambda: "Normal" in state(source, launcher_id))
                time.sleep(0.5)
                assert "Normal" in state(desktop, viewer), "session disposal minimized the app"
                assert console.poll() is None, "session disposal closed the viewer"
                print("PASS transient session iconification returns to launcher", flush=True)
                host_unchanged()

                run(source, "xdotool", "windowunmap", launcher_id)
                wait_for("inner close did not exit viewer", lambda: console.poll() is not None)
                assert not (private / "console-focus").exists(), "stale controller lease"
                assert not (runtime / "uu-remote-console/window.port").exists(), "stale controller port"
                print("PASS inner close cleans viewer and lease", flush=True)
                host_unchanged()
                print("PASS host framebuffer remains identical throughout controller lifecycle", flush=True)
            except Exception:
                for name in ("window-x11vnc.log", "window-viewer.log"):
                    path = root / "state/uu-remote-console" / name
                    if path.exists():
                        print(path.read_text(errors="replace")[-3000:])
                raise
            finally:
                for child in reversed(children):
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=2)


if __name__ == "__main__":
    main()
