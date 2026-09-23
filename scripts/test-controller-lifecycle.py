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

            def display():
                process = subprocess.Popen(
                    ["Xvfb", "-displayfd", "1", "-screen", "0", "1600x1000x24", "-nolisten", "tcp"],
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
                source = display()
                desktop = display()
                (private / "private-display").write_text(source["DISPLAY"] + "\n")
                launcher, launcher_id = app(source, "Lifecycle launcher", "600x450+80+60")
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    port = reservation.getsockname()[1]
                desktop["UURB_CONSOLE_VNC_PORT"] = str(port - 1)
                console = start([str(REPO / "scripts/uu-remote-console"), "window"], desktop)
                viewer = wait_for("viewer did not open", lambda: run(
                    desktop, "xdotool", "search", "--name", "^UU Remote - TigerVNC$"))
                wait_for("launcher not mapped", lambda: "Normal" in state(source, launcher_id))
                time.sleep(0.6)  # Establish the initial source in the real monitor.

                run(source, "xdotool", "windowminimize", launcher_id)
                wait_for("inner minimize did not minimize viewer", lambda: "Iconic" in state(desktop, viewer))
                wait_for("source not restored for taskbar reuse", lambda: "Normal" in state(source, launcher_id))
                run(desktop, "xdotool", "windowmap", viewer, "windowactivate", viewer)
                wait_for("taskbar restore failed", lambda: "Normal" in state(desktop, viewer))
                time.sleep(1)  # Openbox and TigerVNC complete their restore configure events.
                print("PASS inner minimize and taskbar restore", flush=True)

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
                    "140", "120", "click", "1", "key", "a")
                def input_arrived():
                    events = (root / "process.log").read_text(errors="replace")
                    return all(events.count(event) > events_before.count(event)
                               for event in ("ButtonPress event", "KeyPress event"))
                wait_for("scaled viewer did not forward mouse and keyboard", input_arrived)
                print("PASS scaled mouse and keyboard reach source", flush=True)

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

                run(source, "xdotool", "windowunmap", launcher_id)
                wait_for("inner close did not exit viewer", lambda: console.poll() is not None)
                assert not (private / "console-focus").exists(), "stale controller lease"
                assert not (runtime / "uu-remote-console/window.port").exists(), "stale controller port"
                print("PASS inner close cleans viewer and lease", flush=True)
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
