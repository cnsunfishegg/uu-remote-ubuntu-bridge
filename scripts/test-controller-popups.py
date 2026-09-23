#!/usr/bin/env python3
"""Check that the local UU VNC mode shows popups and forwards input.

Uses a disposable Xvfb display and fake X windows; never contacts UU or a
real remote computer.
"""

import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time


def receive(connection: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise RuntimeError("VNC connection closed")
        data.extend(chunk)
    return bytes(data)


def framebuffer(
    connection: socket.socket,
    width: int,
    height: int,
    pixel_bytes: int,
    previous: bytes | None = None,
) -> bytes:
    incremental = 1 if previous is not None else 0
    connection.sendall(bytes((3, incremental)) + struct.pack(">HHHH", 0, 0, width, height))
    header = receive(connection, 4)
    if header[0] != 0:
        raise RuntimeError("VNC did not send a framebuffer update")
    image = bytearray(previous if previous is not None else width * height * pixel_bytes)
    for _ in range(struct.unpack(">H", header[2:4])[0]):
        x, y, rect_width, rect_height, encoding = struct.unpack(
            ">HHHHi", receive(connection, 12)
        )
        if encoding != 0:
            raise RuntimeError(f"unexpected VNC encoding: {encoding}")
        pixels = receive(connection, rect_width * rect_height * pixel_bytes)
        for row in range(rect_height):
            destination = ((y + row) * width + x) * pixel_bytes
            beginning = row * rect_width * pixel_bytes
            image[destination:destination + rect_width * pixel_bytes] = (
                pixels[beginning:beginning + rect_width * pixel_bytes]
            )
    return bytes(image)


def wait_for_resize(
    connection: socket.socket,
    width: int,
    height: int,
    pixel_bytes: int,
    expected: tuple[int, int],
) -> None:
    for _ in range(20):
        connection.sendall(b"\x03\x01" + struct.pack(">HHHH", 0, 0, width, height))
        header = receive(connection, 4)
        if header[0] != 0:
            raise RuntimeError("VNC did not send a framebuffer update")
        for _ in range(struct.unpack(">H", header[2:4])[0]):
            _, _, rect_width, rect_height, encoding = struct.unpack(
                ">HHHHi", receive(connection, 12)
            )
            if encoding == -223:
                if (rect_width, rect_height) != expected:
                    raise RuntimeError("VNC resized to the wrong clip dimensions")
                return
            if encoding != 0:
                raise RuntimeError(f"unexpected VNC encoding: {encoding}")
            receive(connection, rect_width * rect_height * pixel_bytes)
    raise RuntimeError("VNC did not follow the dynamic root clip")


def wait_for_window(environment: dict[str, str], name: str) -> str:
    for _ in range(50):
        result = subprocess.run(
            ["xdotool", "search", "--name", name],
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.splitlines()[-1]
        time.sleep(0.1)
    raise RuntimeError(f"test window did not appear: {name}")


def main() -> None:
    for executable in ("Xvfb", "xev", "xmessage", "xdotool", "x11vnc"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"missing test dependency: {executable}")
    processes: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory(prefix="uu-controller-popups-") as directory:
        root = Path(directory)
        with (root / "xvfb.log").open("wb") as xvfb_log, \
             (root / "xev.log").open("wb") as xev_log, \
             (root / "xmessage.log").open("wb") as popup_log, \
             (root / "x11vnc.log").open("wb") as vnc_log:
            try:
                xvfb = subprocess.Popen(
                    ["Xvfb", "-displayfd", "1", "-screen", "0", "800x600x24",
                     "-nolisten", "tcp"],
                    stdout=subprocess.PIPE,
                    stderr=xvfb_log,
                )
                processes.append(xvfb)
                display = ":" + xvfb.stdout.readline().decode().strip()
                if display == ":":
                    raise RuntimeError("Xvfb did not provide a display")
                environment = {**os.environ, "DISPLAY": display}
                main_window = subprocess.Popen(
                    ["xev", "-name", "UU Root Probe", "-geometry", "400x300+50+50"],
                    env=environment,
                    stdout=xev_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(main_window)
                window = wait_for_window(environment, "UU Root Probe")
                subprocess.run(
                    ["xdotool", "windowfocus", window], env=environment, check=True
                )
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    port = reservation.getsockname()[1]
                channel = f"UURB_TEST_WINDOW_{os.getpid()}"
                vnc = subprocess.Popen(
                    ["x11vnc", "-display", display,
                     "-clip", "400x300+50+50",
                     "-env", f"X11VNC_REMOTE={channel}",
                     "-rfbport", str(port), "-listen", "127.0.0.1",
                     "-localhost", "-nopw", "-once", "-noxdamage",
                     "-nowf", "-noscr", "-quiet"],
                    env=environment,
                    stdout=vnc_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(vnc)
                connection = None
                for _ in range(50):
                    try:
                        connection = socket.create_connection(
                            ("127.0.0.1", port), timeout=1
                        )
                        break
                    except OSError:
                        time.sleep(0.1)
                if connection is None:
                    raise RuntimeError("local VNC listener did not start")
                with connection:
                    connection.settimeout(6)
                    version = receive(connection, 12)
                    connection.sendall(version)
                    count = receive(connection, 1)[0]
                    methods = receive(connection, count)
                    if 1 not in methods:
                        raise RuntimeError("local VNC did not offer no-auth")
                    connection.sendall(b"\x01")
                    if receive(connection, 4) != b"\x00\x00\x00\x00":
                        raise RuntimeError("local VNC security handshake failed")
                    connection.sendall(b"\x01")
                    server = receive(connection, 24)
                    width, height = struct.unpack(">HH", server[:4])
                    if (width, height) != (400, 300):
                        raise RuntimeError("VNC did not expose the initial root clip")
                    receive(connection, struct.unpack(">I", server[20:24])[0])
                    pixel_bytes = server[4] // 8
                    connection.sendall(
                        b"\x02\x00\x00\x02" + struct.pack(">ii", 0, -223)
                    )
                    before = framebuffer(connection, width, height, pixel_bytes)
                    if not any(before):
                        raise RuntimeError("test application's first frame is black")

                    connection.sendall(struct.pack(">BBHH", 5, 1, 80, 80))
                    connection.sendall(struct.pack(">BBHH", 5, 0, 80, 80))
                    connection.sendall(struct.pack(">BBHI", 4, 1, 0, ord("a")))
                    connection.sendall(struct.pack(">BBHI", 4, 0, 0, ord("a")))
                    for _ in range(40):
                        time.sleep(0.1)
                        events = (root / "xev.log").read_text(errors="replace")
                        if "ButtonPress event" in events and "KeyPress event" in events:
                            break
                    else:
                        raise RuntimeError("mouse or keyboard did not reach fake window")

                    popup = subprocess.Popen(
                        ["xmessage", "-title", "UU Popup Probe",
                         "-bg", "red", "-fg", "white",
                         "-geometry", "200x100+150+150", "UU Popup Probe"],
                        env=environment,
                        stdout=popup_log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(popup)
                    popup_window = wait_for_window(environment, "UU Popup Probe")
                    subprocess.run(
                        ["xdotool", "windowmap", popup_window],
                        env=environment,
                        check=True,
                    )
                    subprocess.run(
                        ["xdotool", "windowraise", popup_window],
                        env=environment,
                        check=True,
                    )
                    time.sleep(1.2)
                    for _ in range(15):
                        with_popup = framebuffer(
                            connection, width, height, pixel_bytes, before
                        )
                        changed = sum(a != b for a, b in zip(before, with_popup))
                        if changed >= len(before) // 100:
                            break
                        time.sleep(0.2)
                    if changed < len(before) // 100:
                        raise RuntimeError("separate popup was not visible in VNC")
                    popup_sample = ((150 * width) + 200) * pixel_bytes
                    popup_color = with_popup[popup_sample:popup_sample + pixel_bytes]
                    if not any(popup_color):
                        raise RuntimeError("test popup has no visible color")
                    subprocess.run(
                        ["xdotool", "windowunmap", window],
                        env=environment,
                        check=True,
                    )
                    for _ in range(15):
                        after_hiding_main = framebuffer(
                            connection, width, height, pixel_bytes, with_popup
                        )
                        changed = sum(
                            a != b for a, b in zip(with_popup, after_hiding_main)
                        )
                        if changed >= len(with_popup) // 100:
                            break
                        time.sleep(0.2)
                    if changed < len(with_popup) // 100:
                        raise RuntimeError("VNC did not update after main window hid")
                    if after_hiding_main[popup_sample:popup_sample + pixel_bytes] != popup_color:
                        raise RuntimeError("popup disappeared when the main window hid")
                    print("VNC: clipped root, popup, hidden-main transition, mouse, keyboard passed")

                    remote_window = subprocess.Popen(
                        ["xev", "-name", "UU Remote Session Probe",
                         "-geometry", "600x400+20+20"],
                        env=environment,
                        stdout=xev_log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(remote_window)
                    remote_id = wait_for_window(
                        environment, "UU Remote Session Probe"
                    )
                    subprocess.run(
                        ["xdotool", "windowraise", remote_id],
                        env=environment,
                        check=True,
                    )
                    subprocess.run(
                        ["x11vnc", "-display", display,
                         "-env", f"X11VNC_REMOTE={channel}",
                         "-R", "clip:600x400+20+20"],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                    wait_for_resize(
                        connection, width, height, pixel_bytes, (600, 400)
                    )
                    remote_frame = framebuffer(connection, 600, 400, pixel_bytes)
                    if not any(remote_frame):
                        raise RuntimeError("dynamically clipped session is black")
                    subprocess.run(
                        ["xdotool", "windowsize", remote_id, "700", "500"],
                        env=environment,
                        check=True,
                    )
                    subprocess.run(
                        ["x11vnc", "-display", display,
                         "-env", f"X11VNC_REMOTE={channel}",
                         "-R", "clip:700x500+20+20"],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                    wait_for_resize(
                        connection, 600, 400, pixel_bytes, (700, 500)
                    )
                    resized_frame = framebuffer(connection, 700, 500, pixel_bytes)
                    remote_window.terminate()
                    remote_window.wait(timeout=3)
                    subprocess.run(
                        ["x11vnc", "-display", display,
                         "-env", f"X11VNC_REMOTE={channel}",
                         "-R", "clip:400x300+50+50"],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                    wait_for_resize(
                        connection, 700, 500, pixel_bytes, (400, 300)
                    )
                    returned_frame = framebuffer(connection, 400, 300, pixel_bytes)
                    if not any(returned_frame):
                        raise RuntimeError("root clip did not survive session exit")
                    print("VNC: dynamic session clip, resize, and return continuity passed")

                controller_environment = {
                    **environment,
                    "HOME": str(root),
                    "WINEPREFIX": str(root / "fake-prefix"),
                    "WINE_BIN": "/usr/bin/true",
                    "WINESERVER_BIN": "/usr/bin/true",
                    "UURB_UU_AUDIO": "system",
                }
                controller = subprocess.Popen(
                    [str(Path(__file__).with_name("uu-remote")), "control"],
                    env=controller_environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                processes.append(controller)
                consent_window = wait_for_window(
                    controller_environment, "UU Remote Controller"
                )
                subprocess.run(
                    ["xdotool", "windowfocus", consent_window],
                    env=controller_environment,
                    check=True,
                )
                subprocess.run(
                    ["xdotool", "key", "Return"],
                    env=controller_environment,
                    check=True,
                )
                output, errors = controller.communicate(timeout=5)
                if controller.returncode != 0 or (root / "fake-prefix").exists():
                    raise RuntimeError(
                        f"default Cancel started controller: {output!r} {errors!r}"
                    )
                print("Controller consent: default Cancel leaves host untouched")
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                for process in reversed(processes):
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)


if __name__ == "__main__":
    main()
