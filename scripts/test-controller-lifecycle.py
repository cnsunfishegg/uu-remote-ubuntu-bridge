#!/usr/bin/env python3
"""Run the real console against two isolated X displays, never the user's UU.

Exercises dragging, focus isolation, minimize/restore, transient iconification,
viewport scaling, and inner-close cleanup using real Openbox and TigerVNC.
"""
import ctypes
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


def set_transient_for(env, child, parent):
    """Set the real ICCCM WINDOW property; xprop writes CARDINAL instead."""
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XSetTransientForHint.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong
    ]
    x11.XSetTransientForHint.restype = ctypes.c_int
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(env["DISPLAY"].encode())
    assert display, "could not open fixture display"
    status = x11.XSetTransientForHint(display, int(child), int(parent))
    x11.XSync(display, 0)
    x11.XCloseDisplay(display)
    assert status != 0, "could not set fixture transient hint"


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

            def geometry(env, window):
                return {key: int(value) for key, value in (
                    line.split("=", 1) for line in run(
                        env, "xdotool", "getwindowgeometry", "--shell", window
                    ).splitlines() if "=" in line)}

            def root_geometry(env, window):
                details = run(env, "xwininfo", "-id", window, "-stats")
                labels = {"Absolute upper-left X:": "X", "Absolute upper-left Y:": "Y",
                          "Width:": "WIDTH", "Height:": "HEIGHT"}
                result = {}
                for line in details.splitlines():
                    for label, key in labels.items():
                        if line.strip().startswith(label):
                            result[key] = int(line.rsplit(" ", 1)[-1])
                assert len(result) == 4, details
                return result

            try:
                host = display(two_screens=True)
                source = {**host, "DISPLAY": host["DISPLAY"] + ".1"}
                start(["openbox"], source)
                wait_for("controller WM missing", lambda: "WINDOW" in run(
                    source, "xprop", "-root", "_NET_SUPPORTING_WM_CHECK"))
                desktop = display()
                # The default controller is a single native full-screen shell.
                # This isolated test opts into the diagnostic windowed mode so
                # it can exercise native dragging and arbitrary viewport sizes.
                desktop["UURB_CONTROLLER_FULLSCREEN"] = "off"
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
                def physical_content():
                    return ImageGrab.grab(xdisplay=desktop["DISPLAY"]).crop(
                        (1450, 800, 1550, 900)).tobytes()
                wait_for("host did not paint physical desktop", lambda: host_content() == physical_content())

                def host_unchanged():
                    assert "Normal" in state(host, relay_id), "controller minimized the host relay"
                    assert not (private / "console-focus").exists(), "controller took host focus lease"
                    wait_for("controller overwrote host canvas", lambda: (
                        host_content() == physical_content()))

                launcher, launcher_id = app(source, "Lifecycle launcher", "600x450+80+60")
                # Reproduce a previous bad drag persisted beyond the virtual
                # root before the controller is opened again.
                run(source, "xdotool", "windowmove", launcher_id, "1500", "900")
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    port = reservation.getsockname()[1]
                desktop["UURB_CONSOLE_VNC_PORT"] = str(port - 1)
                console = start([str(REPO / "scripts/uu-remote-console"), "window"], desktop)
                channel = f"UURB_WINDOW_{os.getuid()}_{port}_{console.pid}"
                viewer = wait_for("viewer did not open", lambda: run(
                    desktop, "xdotool", "search", "--name", "^UU Remote - TigerVNC$"))
                wait_for("new viewer did not take keyboard focus", lambda: (
                    run(desktop, "xdotool", "getactivewindow") == viewer))
                wait_for("off-screen launcher not repaired at startup", lambda: (
                    root_geometry(source, launcher_id)["X"] == 1000 and
                    root_geometry(source, launcher_id)["Y"] == 550 and
                    geometry(desktop, viewer)["WIDTH"] == 600 and
                    geometry(desktop, viewer)["HEIGHT"] == 450))
                wait_for("launcher not mapped", lambda: "Normal" in state(source, launcher_id))
                controller_state_file = runtime / "uu-remote-console/controller.state"

                def controller_state():
                    if not controller_state_file.exists():
                        return {}
                    return dict(
                        line.split("=", 1)
                        for line in controller_state_file.read_text().splitlines()
                        if "=" in line
                    )

                wait_for("controller coordinator state is not ready", lambda: (
                    controller_state().get("lifecycle") == "ready" and
                    controller_state().get("candidate_window") == launcher_id and
                    controller_state().get("capture_window") == launcher_id and
                    int(controller_state().get("generation", "0")) >= 1))
                print("PASS coordinator publishes one capture/input state", flush=True)
                wait_for("native titlebar is missing", lambda: "= 1, 1, 22, 5" in run(
                    desktop, "xprop", "-id", viewer, "_NET_FRAME_EXTENTS"))
                print("PASS physical viewer owns a native titlebar", flush=True)
                host_unchanged()
                def canvas_matches():
                    inner = root_geometry(source, launcher_id)
                    outer = root_geometry(desktop, viewer)
                    source_pixels = ImageGrab.grab(xdisplay=source["DISPLAY"]).crop((
                        inner["X"] + 5, inner["Y"] + 5,
                        inner["X"] + 100, inner["Y"] + 100)).tobytes()
                    viewer_pixels = ImageGrab.grab(xdisplay=desktop["DISPLAY"]).crop((
                        outer["X"] + 5, outer["Y"] + 5,
                        outer["X"] + 100, outer["Y"] + 100)).tobytes()
                    return source_pixels == viewer_pixels
                wait_for("viewer crop does not match private client pixels", canvas_matches)
                print("PASS viewer pixels line up with the private client", flush=True)

                outer_before = geometry(desktop, viewer)
                inner_before = root_geometry(source, launcher_id)
                drag_x = outer_before["X"] + outer_before["WIDTH"] // 2
                # xdotool reports the Openbox decoration offset twice.
                drag_y = outer_before["Y"] - 33
                run(desktop, "xdotool", "mousemove", str(drag_x), str(drag_y),
                    "mousedown", "1", "sleep", "0.2", "mousemove",
                    str(drag_x + 30), str(drag_y + 20), "sleep", "0.2",
                    "mousemove", str(drag_x + 120), str(drag_y + 80),
                    "sleep", "0.2", "mouseup", "1")
                try:
                    wait_for("native titlebar did not drag the visible window", lambda: (
                        geometry(desktop, viewer)["X"] == outer_before["X"] + 120 and
                        geometry(desktop, viewer)["Y"] == outer_before["Y"] + 80))
                except AssertionError as error:
                    raise AssertionError((str(error), outer_before,
                                          geometry(desktop, viewer), drag_x, drag_y)) from error
                assert root_geometry(source, launcher_id) == inner_before, (
                    "outer drag moved the private UU window", root_geometry(source, launcher_id))
                print("PASS native drag moves only the physical window", flush=True)
                outer_after_drag = geometry(desktop, viewer)
                run(source, "xdotool", "windowmove", launcher_id, "200", "140")
                try:
                    wait_for("private source did not move", lambda: (
                        root_geometry(source, launcher_id)["X"] == 201 and
                        root_geometry(source, launcher_id)["Y"] == 162))
                except AssertionError as error:
                    raise AssertionError((str(error), outer_after_drag, inner_before,
                                          geometry(desktop, viewer),
                                          root_geometry(source, launcher_id))) from error
                assert geometry(desktop, viewer) == outer_after_drag, (
                    "source motion dragged the physical viewer", geometry(desktop, viewer))
                wait_for("source motion left the viewer pixels behind", canvas_matches)
                run(source, "xdotool", "windowmove", launcher_id, "1500", "900")
                try:
                    wait_for("inner window escaped its root canvas", lambda: (
                        root_geometry(source, launcher_id)["X"] == 1000 and
                        root_geometry(source, launcher_id)["Y"] == 550))
                except AssertionError as error:
                    raise AssertionError((str(error), root_geometry(source, launcher_id),
                                          run(source, "xprop", "-id", launcher_id,
                                              "_NET_FRAME_EXTENTS"))) from error
                assert geometry(desktop, viewer)["WIDTH"] >= 600, (
                    "dragging collapsed the viewer to black", geometry(desktop, viewer))
                assert geometry(desktop, viewer) == outer_after_drag, (
                    "source edge clamp moved the physical viewer", geometry(desktop, viewer))
                wait_for("edge clamp left a black or shifted canvas", canvas_matches)
                print("PASS private source stays within bounds without moving its frame", flush=True)

                # A root-coordinate crop can be perfectly aligned after a
                # drag yet expose the black virtual desktop in intermediate
                # frames. Sample the full visible client while moving it
                # repeatedly, before the shell monitor can catch up.
                misaligned_frames = 0
                for index in range(24):
                    target_x = 200 + (index % 6) * 70
                    target_y = 140 + (index % 6) * 35
                    run(source, "xdotool", "windowmove", launcher_id,
                        str(target_x), str(target_y))
                    if not canvas_matches():
                        misaligned_frames += 1
                assert misaligned_frames == 0, (
                    f"{misaligned_frames} intermediate drag frames exposed the private root")
                print("PASS repeated source motion never exposes a black intermediate frame", flush=True)

                source_box = root_geometry(source, launcher_id)
                popup_x = source_box["X"] + 120
                popup_y = source_box["Y"] + 110
                popup = start(["xmessage", "-name", "Lifecycle popup",
                               "-bg", "#ff0000", "-fg", "#ff0000",
                               "-geometry", f"160x110+{popup_x}+{popup_y}",
                               "Overlay"], source)
                popup_id = wait_for("popup fixture missing", lambda: run(
                    source, "xdotool", "search", "--name", "^Lifecycle popup$"))
                run(source, "xdotool", "set_window", "--class", "gameviewer.exe",
                    popup_id.splitlines()[-1])
                run(source, "xdotool", "windowactivate", popup_id.splitlines()[-1])
                popup_box = root_geometry(source, popup_id.splitlines()[-1])
                sample_x = popup_box["X"] + 75
                sample_y = popup_box["Y"] + 60
                def source_popup_red():
                    return ImageGrab.grab(xdisplay=source["DISPLAY"]).getpixel((
                        sample_x, sample_y))[:3] == (255, 0, 0)
                wait_for("popup did not paint over private source", source_popup_red)
                outer_box = root_geometry(desktop, viewer)
                popup_sample = (outer_box["X"] + sample_x - source_box["X"],
                                outer_box["Y"] + sample_y - source_box["Y"])
                try:
                    wait_for("automatic shifted capture did not reveal popup", lambda: (
                        ImageGrab.grab(xdisplay=desktop["DISPLAY"]).getpixel(
                            popup_sample)[:3] == (255, 0, 0)))
                    wait_for("popup did not select refreshed shifted capture", lambda: (
                        controller_state().get("capture_mode") == "sid" and
                        controller_state().get("capture_window") == launcher_id))
                except AssertionError as error:
                    raise AssertionError((str(error), popup_sample,
                        popup.poll(), state(source, popup_id.splitlines()[-1]),
                        run(source, "xdotool", "getactivewindow"),
                        run(source, "xprop", "-id", popup_id.splitlines()[-1], "WM_CLASS"),
                        source_box, popup_box,
                        run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel, "-Q", "sid"),
                        run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel, "-Q", "id"))) from error
                print("PASS temporary shifted capture shows private popup", flush=True)
                run(desktop, "xdotool", "mousemove", "--window", viewer,
                    str(popup_sample[0] - outer_box["X"]),
                    str(popup_sample[1] - outer_box["Y"]), "click", "1")
                popup_pointer = {key: int(value) for key, value in (
                    line.split("=", 1) for line in run(
                        source, "xdotool", "getmouselocation", "--shell"
                    ).splitlines() if line.startswith(("X=", "Y=")))}
                assert abs(popup_pointer["X"] - sample_x) <= 2, popup_pointer
                assert abs(popup_pointer["Y"] - sample_y) <= 2, popup_pointer
                assert popup.poll() is None, "popup closed unexpectedly during input"
                print("PASS popup receives pointer input", flush=True)
                popup.terminate()
                popup.wait(timeout=3)
                wait_for("direct capture did not return after popup", lambda: (
                    hex(int(launcher_id)) in run(source, "x11vnc", "-env",
                        "X11VNC_REMOTE=" + channel, "-Q", "id")))
                try:
                    wait_for("direct capture did not recover after popup", canvas_matches)
                except AssertionError as error:
                    raise AssertionError((str(error), controller_state(),
                        run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel,
                            "-Q", "id"),
                        run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel,
                            "-Q", "clip"),
                        root_geometry(source, launcher_id),
                        root_geometry(desktop, viewer))) from error

                run(desktop, "xdotool", "windowminimize", viewer)
                wait_for("native minimize failed", lambda: "Iconic" in state(desktop, viewer))
                assert "Normal" in state(source, launcher_id), "native minimize hid UU source"
                run(desktop, "xdotool", "windowmap", viewer, "windowactivate", viewer)
                wait_for("native taskbar restore failed", lambda: "Normal" in state(desktop, viewer))
                print("PASS native minimize and restore keep the source painted", flush=True)

                run(source, "xdotool", "windowminimize", launcher_id)
                wait_for("inner minimize did not minimize viewer", lambda: "Iconic" in state(desktop, viewer))
                wait_for("source not restored for taskbar reuse", lambda: "Normal" in state(source, launcher_id))
                run(desktop, "xdotool", "windowmap", viewer, "windowactivate", viewer)
                wait_for("taskbar restore failed", lambda: "Normal" in state(desktop, viewer))
                time.sleep(1)  # Openbox and TigerVNC complete their restore configure events.
                print("PASS inner minimize and taskbar restore", flush=True)
                host_unchanged()

                run(desktop, "xdotool", "windowsize", viewer, "420", "330")
                # Remote commands share one X property. Polling -Q rapidly
                # can overwrite the monitor's pending -R scale request.
                time.sleep(2)
                answer = run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel, "-Q", "scale")
                assert "ans=scale:0.700000" in answer, (
                    "viewport scaling was not applied: " + answer + " / " +
                    run(desktop, "xdotool", "getwindowgeometry", "--shell", viewer))
                print("PASS smaller viewport scales the complete source", flush=True)
                scaled_outer = geometry(desktop, viewer)
                for step in ((993, 501), (988, 496)):
                    run(source, "xdotool", "windowmove", launcher_id,
                        str(step[0]), str(step[1]))
                    time.sleep(0.7)
                assert geometry(desktop, viewer) == scaled_outer, (
                    "scaled source movement dragged the physical viewer", geometry(desktop, viewer))
                def current_source():
                    return run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel,
                               "-Q", "id")
                wait_for("window-bound VNC capture lost its source", lambda: (
                    hex(int(launcher_id)) in current_source()))
                def scaled_viewer_painted():
                    outer = root_geometry(desktop, viewer)
                    return ImageGrab.grab(xdisplay=desktop["DISPLAY"]).getpixel((
                        outer["X"] + 200, outer["Y"] + 100))[:3] == (255, 255, 255)
                wait_for("window-bound capture went black after drag", scaled_viewer_painted)
                assert "0.700000" in run(source, "x11vnc", "-env", "X11VNC_REMOTE=" + channel,
                                          "-Q", "scale"), "source movement reset viewport scaling"
                print("PASS scaled source motion leaves the physical frame alone", flush=True)
                events_before = (root / "process.log").read_text(errors="replace")
                run(desktop, "xdotool", "mousemove", "--window", viewer,
                    "210", "165", "click", "1", "key", "a")
                def input_arrived():
                    events = (root / "process.log").read_text(errors="replace")
                    return all(events.count(event) > events_before.count(event)
                               for event in ("ButtonPress event", "KeyPress event"))
                wait_for("scaled viewer did not forward mouse and keyboard", input_arrived)
                pointer = dict(line.split("=", 1) for line in run(source, "xdotool", "getmouselocation", "--shell").splitlines())
                source_geometry = root_geometry(source, launcher_id)
                # Test the viewport center; TigerVNC centers the 420x315
                # framebuffer within the taller 420x330 viewport.
                assert abs(int(pointer["X"]) - source_geometry["X"] - 300) <= 2, (pointer, source_geometry)
                assert abs(int(pointer["Y"]) - source_geometry["Y"] - 225) <= 2, (pointer, source_geometry)
                print("PASS scaled mouse and keyboard reach source", flush=True)

                local_log_path = root / "local-input.log"
                with local_log_path.open("wb") as local_log:
                    local_input = subprocess.Popen(
                        ["xev", "-name", "Local typing fixture", "-geometry", "200x150+0+700"],
                        env=desktop, stdout=local_log, stderr=log)
                    children.append(local_input)
                    local_id = wait_for("local input fixture missing", lambda: run(
                        desktop, "xdotool", "search", "--name", "^Local typing fixture$"))
                    run(desktop, "xdotool", "windowactivate", local_id.splitlines()[-1])
                    remote_before = (root / "process.log").read_text(errors="replace").count("KeyPress event")
                    run(desktop, "xdotool", "key", "b")
                    wait_for("local typing did not reach local fixture", lambda: (
                        "KeyPress event" in local_log_path.read_text(errors="replace")))
                    assert (root / "process.log").read_text(errors="replace").count(
                        "KeyPress event") == remote_before, "local typing leaked to remote"
                    local_before = local_log_path.read_text(errors="replace").count("KeyPress event")
                    run(desktop, "xdotool", "mousemove", "--window", viewer,
                        "210", "165", "click", "1", "key", "c")
                    wait_for("remote typing did not reach remote fixture", lambda: (
                        (root / "process.log").read_text(errors="replace").count(
                            "KeyPress event") > remote_before))
                    assert local_log_path.read_text(errors="replace").count(
                        "KeyPress event") == local_before, "remote typing leaked to local app"
                    local_input.terminate()
                    local_input.wait(timeout=3)
                print("PASS keyboard goes only to the focused local or remote window", flush=True)

                viewer_state_before = run(
                    desktop, "xprop", "-id", viewer, "_NET_WM_STATE")
                run(source, "wmctrl", "-ir", hex(int(launcher_id)), "-b",
                    "add,maximized_vert,maximized_horz")
                wait_for("private maximize did not apply", lambda: "MAXIMIZED_VERT" in run(
                    source, "xprop", "-id", launcher_id, "_NET_WM_STATE"))
                assert run(desktop, "xprop", "-id", viewer,
                           "_NET_WM_STATE") == viewer_state_before, (
                    "private controls changed the presentation shell")
                run(source, "wmctrl", "-ir", hex(int(launcher_id)), "-b",
                    "remove,maximized_vert,maximized_horz")
                wait_for("private restore did not apply", lambda: "MAXIMIZED_VERT" not in run(
                    source, "xprop", "-id", launcher_id, "_NET_WM_STATE"))
                print("PASS UU controls do not create a second shell state", flush=True)

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
                assert not controller_state_file.exists(), "stale controller state"
                print("PASS inner close cleans viewer and lease", flush=True)
                host_unchanged()
                print("PASS host framebuffer remains identical throughout controller lifecycle", flush=True)

                # Automatic presentation is the normal user path: the UU
                # launcher is a borderless app-sized window, a remote canvas
                # gets a freshly-created full-screen viewer, and destroying
                # that canvas returns to a fresh launcher viewer even when
                # x11vnc exits before its monitor sees the scene change.
                desktop["UURB_CONTROLLER_FULLSCREEN"] = "auto"
                manager, manager_id = app(
                    source, "Lifecycle manager", "920x680+200+120")
                run(source, "xdotool", "set_window", "--name", "网易UU远程",
                    manager_id)
                wait_for("localized manager title was not applied", lambda: (
                    run(source, "xdotool", "getwindowname", manager_id) ==
                    "网易UU远程"))
                console = start([str(REPO / "scripts/uu-remote-console"), "window"], desktop)

                def active_controller_state(expected_mode, expected_window):
                    current = controller_state()
                    return (
                        current.get("lifecycle") == "ready" and
                        current.get("presentation_mode") == expected_mode and
                        current.get("candidate_window") == expected_window
                    )

                wait_for("automatic launcher did not open windowed", lambda: (
                    active_controller_state("windowed", manager_id)))
                viewer = wait_for("automatic launcher viewer missing", lambda: run(
                    desktop, "xdotool", "search", "--name", "^UU Remote - TigerVNC$"))
                wait_for("automatic launcher kept a second Linux titlebar", lambda: (
                    "= 0, 0, 0, 0" in run(
                        desktop, "xprop", "-id", viewer.splitlines()[-1],
                        "_NET_FRAME_EXTENTS")))
                assert geometry(desktop, viewer.splitlines()[-1])["WIDTH"] == 920
                assert geometry(desktop, viewer.splitlines()[-1])["HEIGHT"] == 680
                print("PASS automatic device list is one borderless 920x680 window", flush=True)

                enter_started = time.monotonic()
                session, session_id = app(source, "Lifecycle remote canvas", "640x360+0+0")
                run(source, "xprop", "-id", session_id, "-f",
                    "_NET_WM_WINDOW_TYPE", "32a", "-set",
                    "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_NORMAL")
                run(source, "xdotool", "windowminimize", manager_id)
                run(source, "xdotool", "windowactivate", session_id)
                try:
                    wait_for(
                        "remote canvas did not recreate a full-screen viewer",
                        lambda: active_controller_state("fullscreen", session_id),
                        timeout=20,
                    )
                except AssertionError as error:
                    raise AssertionError((
                        str(error),
                        "active=" + run(source, "xdotool", "getactivewindow"),
                        "windows=" + run(source, "wmctrl", "-lGx"),
                        "properties=" + run(
                            source,
                            "xprop",
                            "-id",
                            session_id,
                            "WM_STATE",
                            "_NET_WM_WINDOW_TYPE",
                            "WM_TRANSIENT_FOR",
                        ),
                        "geometry=" + str(root_geometry(source, session_id)),
                        "state=" + str(controller_state()),
                    )) from error
                current = controller_state()
                remote_geometry = root_geometry(source, session_id)
                assert remote_geometry["WIDTH"] == 1600, remote_geometry
                # A decorated test window uses 21 vertical pixels for its
                # Openbox frame. Real UU is borderless and reaches 1920x1080.
                assert remote_geometry["HEIGHT"] >= 936, remote_geometry
                assert current.get("source_width") == "1600", current
                assert int(current.get("source_height", "0")) >= 936, current
                assert current.get("viewer_maximized") == "true", current

                def focused_fullscreen_viewer():
                    viewer = controller_state().get("viewer_window", "0")
                    if (int(viewer) > 0 and
                            run(desktop, "xdotool", "getactivewindow") == viewer):
                        return viewer
                    return ""

                fullscreen_viewer = wait_for(
                    "full-screen viewer was not focused before first input",
                    focused_fullscreen_viewer,
                )
                current = controller_state()
                assert current.get("scale") == "1.000000", current
                assert current.get("capture_mode") == "root-clip", current
                enter_elapsed = time.monotonic() - enter_started
                print(
                    "PASS bootstrap canvas reaches native resolution before "
                    "full-screen and owns first input on "
                    f"first frame ({enter_elapsed:.2f}s)", flush=True)

                # UU 4.39 implements its exit confirmation as a second,
                # opaque black full-screen DirectX window with only a small
                # confirmation card painted in the centre.  The controller
                # must retain the remote canvas as its primary scene and
                # shape that transient surface down to the visible card.
                session_hex = f"0x{int(session_id):x}"
                run(source, "wmctrl", "-ir", session_hex, "-b", "add,fullscreen")
                wait_for("remote fixture did not become exactly full-screen", lambda: (
                    root_geometry(source, session_id)["WIDTH"] == 1600 and
                    root_geometry(source, session_id)["HEIGHT"] == 1000))
                wait_for("controller missed exact full-screen source geometry", lambda: (
                    controller_state().get("source_width") == "1600" and
                    controller_state().get("source_height") == "1000"))
                confirmation, confirmation_id = app(
                    source, "Lifecycle exit confirmation", "448x176+576+412")
                confirmation_hex = f"0x{int(confirmation_id):x}"
                set_transient_for(source, confirmation_id, session_id)
                run(source, "xprop", "-id", confirmation_id, "-f",
                    "_NET_WM_WINDOW_TYPE", "32a", "-set",
                    "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DIALOG")
                run(source, "wmctrl", "-ir", confirmation_hex, "-b",
                    "add,fullscreen")
                run(source, "xdotool", "windowactivate", confirmation_id)

                def confirmation_is_shaped():
                    current = controller_state()
                    shape = run(source, "xwininfo", "-id", confirmation_id,
                                "-shape")
                    return (
                        current.get("candidate_window") == session_id and
                        current.get("overlay_window") == confirmation_id and
                        "Window shape extents:  448x176+576+412" in shape
                    )

                try:
                    wait_for(
                        "full-screen exit confirmation kept its black backing",
                        confirmation_is_shaped,
                    )
                except AssertionError as error:
                    raise AssertionError((
                        str(error),
                        "state=" + str(controller_state()),
                        "windows=" + run(source, "wmctrl", "-lGx"),
                        "properties=" + run(
                            source, "xprop", "-id", confirmation_id,
                            "WM_STATE", "_NET_WM_WINDOW_TYPE",
                            "_NET_WM_STATE", "WM_TRANSIENT_FOR"),
                        "shape=" + run(
                            source, "xwininfo", "-id", confirmation_id,
                            "-shape"),
                    )) from error
                print(
                    "PASS exit confirmation preserves the remote picture "
                    "behind its 448x176 card", flush=True)
                confirmation.terminate()
                confirmation.wait(timeout=3)
                run(source, "xdotool", "windowactivate", session_id)
                wait_for("closed confirmation remained the active overlay", lambda: (
                    controller_state().get("overlay_window") != confirmation_id))

                # Reproduce the real UU ordering: its remote window disappears
                # first, the launcher becomes visible shortly afterwards.
                exit_started = time.monotonic()
                session.terminate()
                session.wait(timeout=3)
                time.sleep(0.4)
                run(source, "xdotool", "windowmap", manager_id,
                    "windowactivate", manager_id)
                wait_for("remote exit did not recreate the launcher viewer", lambda: (
                    active_controller_state("windowed", manager_id)), timeout=20)
                viewer = wait_for("returned launcher viewer missing", lambda: run(
                    desktop, "xdotool", "search", "--name", "^UU Remote - TigerVNC$"))
                wait_for("returned launcher regained a Linux titlebar", lambda: (
                    "= 0, 0, 0, 0" in run(
                        desktop, "xprop", "-id", viewer.splitlines()[-1],
                        "_NET_FRAME_EXTENTS")))
                assert console.poll() is None, "automatic controller exited instead of returning"
                exit_elapsed = time.monotonic() - exit_started
                print(
                    "PASS remote exit automatically returns to the device list "
                    f"without F8 ({exit_elapsed:.2f}s)", flush=True)

                run(source, "xdotool", "windowunmap", manager_id)
                wait_for("automatic controller did not close with its launcher", lambda: (
                    console.poll() is not None))
                host_unchanged()
            except Exception:
                for name in (
                    "window-x11vnc.log",
                    "window-viewer.log",
                    "window-timing.log",
                ):
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
