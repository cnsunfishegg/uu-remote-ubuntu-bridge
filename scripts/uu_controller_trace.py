#!/usr/bin/env python3
"""Trace the local UU controller input boundary without recording typed text."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable


EVENT_HEADER = re.compile(r"^EVENT type \d+ \(([^)]+)\)$")
DEVICE = re.compile(r"^\s*device:\s*(\d+)")
EVENT_TIME = re.compile(r"^\s*time:\s*(\d+)")
DETAIL = re.compile(r"^\s*detail:\s*(\d+)")
ROOT_COORDS = re.compile(r"^\s*root:\s*(-?[0-9.]+)/(-?[0-9.]+)")
WINDOWS = re.compile(
    r"^\s*windows:\s*root\s+(0x[0-9a-f]+)\s+event\s+(0x[0-9a-f]+)"
    r"\s+child\s+(0x[0-9a-f]+)",
    re.IGNORECASE,
)
DISPLAY_NAME = re.compile(r"^:[0-9]{1,3}(?:\.[0-9]+)?$")
RAW_KINDS = {"RawButtonPress", "RawButtonRelease", "RawKeyPress", "RawKeyRelease"}


class TraceError(RuntimeError):
    """A user-actionable trace preflight failure."""


@dataclass
class InputEvent:
    layer: str
    kind: str
    observed_ms: int
    server_time: int | None
    target: str
    active_window: str | None
    event_window: str | None
    child_window: str | None
    x: float | None
    y: float | None
    button: int | None = None
    generation: int | None = None


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 3,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or command[0]
        raise TraceError(message)
    return result


def xenv(display: str, authority: Path | None) -> dict[str, str]:
    environment = dict(os.environ)
    environment["DISPLAY"] = display
    if authority is not None:
        environment["XAUTHORITY"] = str(authority)
    else:
        environment.pop("XAUTHORITY", None)
    return environment


def parse_window_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def hex_window(value: int | None) -> str | None:
    return None if value is None else hex(value)


def read_x_active_window(environment: dict[str, str]) -> int | None:
    result = run(
        ["/usr/bin/xprop", "-root", "_NET_ACTIVE_WINDOW"],
        env=environment,
        timeout=1,
        check=False,
    )
    match = re.search(r"window id #\s*(0x[0-9a-f]+|0)", result.stdout, re.I)
    return parse_window_id(match.group(1)) if match else None


def window_class(environment: dict[str, str], window: int | None) -> str:
    if not window:
        return ""
    result = run(
        ["/usr/bin/xprop", "-id", str(window), "WM_CLASS"],
        env=environment,
        timeout=1,
        check=False,
    )
    return result.stdout.lower()


def window_geometry(environment: dict[str, str], window: int) -> dict[str, int]:
    result = run(
        ["/usr/bin/xwininfo", "-id", str(window), "-stats"],
        env=environment,
    )
    patterns = {
        "x": r"Absolute upper-left X:\s*(-?\d+)",
        "y": r"Absolute upper-left Y:\s*(-?\d+)",
        "width": r"^\s*Width:\s*(\d+)",
        "height": r"^\s*Height:\s*(\d+)",
    }
    geometry: dict[str, int] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, result.stdout, re.MULTILINE)
        if not match:
            raise TraceError(f"Could not read {key} for X window {hex(window)}")
        geometry[key] = int(match.group(1))
    return geometry


def xinput_master_ids(environment: dict[str, str]) -> tuple[int, int]:
    output = run(["/usr/bin/xinput", "list", "--short"], env=environment).stdout
    pointer = re.search(r"id=(\d+)\s*\[master pointer", output)
    keyboard = re.search(r"id=(\d+)\s*\[master keyboard", output)
    if not pointer or not keyboard:
        raise TraceError("Could not find the XInput master pointer and keyboard")
    return int(pointer.group(1)), int(keyboard.group(1))


def parse_event_block(
    lines: list[str],
    *,
    layer: str,
    observed_ms: int,
    pointer_master: int,
    keyboard_master: int,
    snapshot: Callable[
        [str, int | None, int | None],
        tuple[str, int | None, float | None, float | None, int | None],
    ],
) -> InputEvent | None:
    if not lines:
        return None
    header = EVENT_HEADER.match(lines[0])
    if not header or header.group(1) not in RAW_KINDS:
        return None
    kind = header.group(1).removeprefix("Raw")
    device = None
    server_time = None
    detail = None
    x = None
    y = None
    event_window = None
    child_window = None
    for line in lines[1:]:
        match = DEVICE.match(line)
        if match:
            device = int(match.group(1))
            continue
        match = EVENT_TIME.match(line)
        if match:
            server_time = int(match.group(1))
            continue
        match = DETAIL.match(line)
        if match:
            detail = int(match.group(1))
            continue
        match = ROOT_COORDS.match(line)
        if match:
            x, y = float(match.group(1)), float(match.group(2))
            continue
        match = WINDOWS.match(line)
        if match:
            event_window = int(match.group(2), 16)
            child_window = int(match.group(3), 16)
    expected = keyboard_master if kind.startswith("Key") else pointer_master
    if device != expected:
        return None
    target, active_window, snapshot_x, snapshot_y, generation = snapshot(
        kind, event_window, child_window
    )
    if x is None:
        x = snapshot_x
    if y is None:
        y = snapshot_y
    return InputEvent(
        layer=layer,
        kind=kind,
        observed_ms=observed_ms,
        server_time=server_time,
        target=target,
        active_window=hex_window(active_window),
        event_window=hex_window(event_window),
        child_window=hex_window(child_window),
        x=x,
        y=y,
        button=detail if kind.startswith("Button") else None,
        generation=generation,
    )


class XInputCollector(threading.Thread):
    def __init__(
        self,
        *,
        layer: str,
        environment: dict[str, str],
        started: float,
        snapshot: Callable[
            [str, int | None, int | None],
            tuple[str, int | None, float | None, float | None, int | None],
        ],
    ) -> None:
        super().__init__(name=f"uu-input-{layer}", daemon=True)
        self.layer = layer
        self.environment = environment
        self.started = started
        self.snapshot = snapshot
        self.pointer_master, self.keyboard_master = xinput_master_ids(environment)
        self.events: list[InputEvent] = []
        self.error: str | None = None
        self.process: subprocess.Popen[str] | None = None
        self.ready = threading.Event()

    def run(self) -> None:
        try:
            self.process = subprocess.Popen(
                ["/usr/bin/stdbuf", "-oL", "/usr/bin/xinput", "test-xi2", "--root"],
                env=self.environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
            self.ready.set()
            assert self.process.stdout is not None
            block: list[str] = []
            block_time = 0
            for raw_line in self.process.stdout:
                line = raw_line.rstrip("\n")
                if EVENT_HEADER.match(line):
                    self._finish(block, block_time)
                    block = [line]
                    block_time = int((time.monotonic() - self.started) * 1000)
                elif block:
                    block.append(line)
            self._finish(block, block_time)
            returncode = self.process.wait(timeout=2)
            if returncode not in (0, -signal.SIGTERM):
                assert self.process.stderr is not None
                self.error = self.process.stderr.read().strip() or "xinput exited"
        except Exception as exc:  # Keep the other collector and report both layers.
            self.error = str(exc)
            self.ready.set()
        finally:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
                if self.process.stdout is not None:
                    self.process.stdout.close()
                if self.process.stderr is not None:
                    self.process.stderr.close()

    def _finish(self, block: list[str], observed_ms: int) -> None:
        event = parse_event_block(
            block,
            layer=self.layer,
            observed_ms=observed_ms,
            pointer_master=self.pointer_master,
            keyboard_master=self.keyboard_master,
            snapshot=self.snapshot,
        )
        if event is None:
            return
        if len(self.events) < 512:
            self.events.append(event)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()


def pointer_location(environment: dict[str, str]) -> tuple[float | None, float | None, int | None]:
    result = run(
        ["/usr/bin/xdotool", "getmouselocation", "--shell"],
        env=environment,
        timeout=1,
        check=False,
    )
    fields = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    try:
        x = float(fields["X"])
        y = float(fields["Y"])
    except (KeyError, ValueError):
        x, y = None, None
    return x, y, parse_window_id(fields.get("WINDOW"))


def point_inside(
    x: float | None, y: float | None, geometry: dict[str, int] | None
) -> bool:
    if x is None or y is None or geometry is None:
        return False
    return (
        geometry["x"] <= x < geometry["x"] + geometry["width"]
        and geometry["y"] <= y < geometry["y"] + geometry["height"]
    )


def read_controller_state(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    state: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z_]+", key) and re.fullmatch(
            r"[A-Za-z0-9.:-]+", value
        ):
            state[key] = value
    return state


class PointerPoller(threading.Thread):
    def __init__(
        self,
        *,
        layer: str,
        environment: dict[str, str],
        geometry: dict[str, int] | None = None,
    ) -> None:
        super().__init__(name=f"uu-pointer-{layer}", daemon=True)
        self.layer = layer
        self.environment = environment
        self.geometry = geometry
        self.motion_count = 0
        self.error: str | None = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        previous: tuple[float | None, float | None] | None = None
        try:
            while not self._stop_event.is_set():
                x, y, _window = pointer_location(self.environment)
                current = (x, y)
                if (
                    previous is not None
                    and None not in current
                    and current != previous
                    and (self.geometry is None or point_inside(x, y, self.geometry))
                ):
                    self.motion_count += 1
                previous = current
                self._stop_event.wait(0.05)
        except Exception as exc:
            self.error = str(exc)

    def stop(self) -> None:
        self._stop_event.set()


def process_arguments(pid: int) -> list[str]:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode(
            "utf-8", errors="replace"
        ).split("\0")[:-1]
    except (OSError, UnicodeError):
        return []


def find_controller_x11vnc(controller_display: str, wanted_port: str | None) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        arguments = process_arguments(int(entry.name))
        if not arguments or Path(arguments[0]).name != "x11vnc":
            continue
        values: dict[str, str] = {}
        flags: set[str] = set()
        index = 1
        while index < len(arguments):
            argument = arguments[index]
            if argument in {"-display", "-auth", "-id", "-sid", "-rfbport", "-env"}:
                if index + 1 < len(arguments):
                    values[argument] = arguments[index + 1]
                    index += 2
                    continue
            if argument in {"-viewonly", "-always_inject", "-xwarppointer", "-nocursorpos"}:
                flags.add(argument)
            index += 1
        remote = values.get("-env", "")
        if values.get("-display") != controller_display or not remote.startswith(
            "X11VNC_REMOTE=UURB_WINDOW_"
        ):
            continue
        if wanted_port and values.get("-rfbport") != wanted_port:
            continue
        matches.append(
            {
                "pid": int(entry.name),
                "display": values.get("-display"),
                "auth": values.get("-auth"),
                "id": values.get("-id"),
                "sid": values.get("-sid"),
                "port": values.get("-rfbport"),
                "remote": remote.removeprefix("X11VNC_REMOTE="),
                "flags": sorted(flags),
            }
        )
    if len(matches) != 1:
        raise TraceError(
            f"Expected one controller x11vnc process, found {len(matches)}; open UU Remote first"
        )
    return matches[0]


def query_x11vnc(
    process: dict[str, object], environment: dict[str, str]
) -> dict[str, str]:
    remote = str(process["remote"])
    result = run(
        [
            "/usr/bin/x11vnc",
            "-env",
            f"X11VNC_REMOTE={remote}",
            "-Q",
            "id,sid,scale,input,viewonly,always_inject,xwarp",
        ],
        env=environment,
        timeout=2,
        check=False,
    )
    output = result.stdout + result.stderr
    return dict(re.findall(r"ans=([^:,\s]+):([^,\n]+)", output))


def find_viewer_pid(port: str) -> int:
    endpoint = f"127.0.0.1::{port}"
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        arguments = process_arguments(int(entry.name))
        if arguments and Path(arguments[0]).name == "vncviewer" and endpoint in arguments:
            matches.append(int(entry.name))
    if len(matches) != 1:
        raise TraceError(f"Expected one TigerVNC viewer for {endpoint}, found {len(matches)}")
    return matches[0]


def find_viewer_window(pid: int, environment: dict[str, str]) -> int:
    result = run(
        ["/usr/bin/xdotool", "search", "--onlyvisible", "--pid", str(pid)],
        env=environment,
        check=False,
    )
    windows = [int(value) for value in result.stdout.split() if value.isdigit()]
    if not windows:
        result = run(
            ["/usr/bin/xdotool", "search", "--pid", str(pid)],
            env=environment,
            check=False,
        )
        windows = [int(value) for value in result.stdout.split() if value.isdigit()]
    if not windows:
        raise TraceError("The UU TigerVNC viewer window is unavailable")
    return windows[-1]


def target_classifier(
    environment: dict[str, str],
    *,
    expected_window: int,
    expected_class: str,
    expected_geometry: dict[str, int],
    controller_state_file: Path,
) -> Callable[
    [str, int | None, int | None],
    tuple[str, int | None, float | None, float | None, int | None],
]:
    class_cache: dict[int, str] = {}

    def classify(
        kind: str, event_window: int | None, child_window: int | None
    ) -> tuple[str, int | None, float | None, float | None, int | None]:
        active = read_x_active_window(environment)
        pointer_x, pointer_y, pointer_window = pointer_location(environment)
        state = read_controller_state(controller_state_file)
        try:
            generation = int(state["generation"])
        except (KeyError, ValueError):
            generation = None
        if expected_class == "viewer" and kind.startswith("Button"):
            target = "viewer" if point_inside(
                pointer_x, pointer_y, expected_geometry
            ) else "other"
            return target, active, pointer_x, pointer_y, generation
        candidates = [
            value
            for value in (active, event_window, child_window, pointer_window)
            if value
        ]
        if expected_window in candidates:
            return expected_class, active, pointer_x, pointer_y, generation
        for candidate in candidates:
            if candidate not in class_cache:
                class_cache[candidate] = window_class(environment, candidate)
            current_class = class_cache[candidate]
            if expected_class == "viewer" and "tigervnc" in current_class:
                return "viewer", active, pointer_x, pointer_y, generation
            if expected_class == "uu" and "gameviewer.exe" in current_class:
                return "uu", active, pointer_x, pointer_y, generation
        if kind.startswith("Button") and point_inside(
            pointer_x, pointer_y, expected_geometry
        ):
            return expected_class, active, pointer_x, pointer_y, generation
        return "other", active, pointer_x, pointer_y, generation

    return classify


def greedy_pairs(
    first: Iterable[InputEvent], second: Iterable[InputEvent], *, window_ms: int = 1200
) -> int:
    available = list(second)
    paired = 0
    for event in first:
        for index, candidate in enumerate(available):
            if candidate.observed_ms < event.observed_ms - 100:
                continue
            if candidate.observed_ms > event.observed_ms + window_ms:
                break
            if event.button is not None and candidate.button != event.button:
                continue
            paired += 1
            available.pop(index)
            break
    return paired


def summarize(events: list[InputEvent], motion: dict[str, int]) -> dict[str, object]:
    outer_buttons = [
        event
        for event in events
        if event.layer == "physical"
        and event.kind == "ButtonPress"
        and event.target == "viewer"
    ]
    inner_buttons = [
        event
        for event in events
        if event.layer == "controller"
        and event.kind == "ButtonPress"
        and event.target == "uu"
    ]
    outer_keys = [
        event
        for event in events
        if event.layer == "physical"
        and event.kind == "KeyPress"
        and event.target == "viewer"
    ]
    inner_keys = [
        event
        for event in events
        if event.layer == "controller"
        and event.kind == "KeyPress"
        and event.target == "uu"
    ]
    local_keys = [
        event
        for event in events
        if event.layer == "physical"
        and event.kind == "KeyPress"
        and event.target != "viewer"
    ]
    paired_buttons = greedy_pairs(outer_buttons, inner_buttons)
    paired_keys = greedy_pairs(outer_keys, inner_keys)
    possible_focus_leaks = greedy_pairs(local_keys, inner_keys, window_ms=500)
    if possible_focus_leaks:
        verdict = "focus_leak_suspected"
    elif outer_buttons and not inner_buttons:
        verdict = "viewer_received_button_but_private_uu_did_not"
    elif outer_keys and not inner_keys:
        verdict = "viewer_received_key_but_private_uu_did_not"
    elif paired_buttons or paired_keys:
        verdict = "input_reached_private_uu_window"
    elif motion.get("physical", 0) and not motion.get("controller", 0):
        verdict = "viewer_pointer_moved_but_private_pointer_did_not"
    elif motion.get("physical", 0) and motion.get("controller", 0):
        verdict = "pointer_motion_reached_private_display"
    else:
        verdict = "no_decisive_input_sample"
    return {
        "physical_motion_events": motion.get("physical", 0),
        "controller_motion_events": motion.get("controller", 0),
        "viewer_button_presses": len(outer_buttons),
        "uu_button_presses": len(inner_buttons),
        "paired_button_presses": paired_buttons,
        "viewer_key_presses": len(outer_keys),
        "uu_key_presses": len(inner_keys),
        "paired_key_presses": paired_keys,
        "local_key_presses": len(local_keys),
        "possible_focus_leaks": possible_focus_leaks,
        "controller_generations": sorted(
            {event.generation for event in events if event.generation is not None}
        ),
        "verdict": verdict,
        "remote_target_observation_required": True,
    }


def default_output() -> Path:
    state_home = Path(
        os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return state_home / "uu-remote" / f"controller-trace-{stamp}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the Ubuntu -> UU controller input boundary without key contents"
    )
    parser.add_argument("--duration", type=int, default=15, choices=range(3, 121))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for dependency in ("xinput", "xdotool", "xprop", "xwininfo", "x11vnc", "stdbuf"):
        if shutil.which(dependency) is None:
            raise TraceError(f"Missing trace dependency: {dependency}")

    physical_display = os.environ.get("DISPLAY", "")
    if not DISPLAY_NAME.fullmatch(physical_display):
        raise TraceError("Run this command from the logged-in Ubuntu graphical desktop")
    physical_authority_value = os.environ.get("XAUTHORITY")
    physical_authority = (
        Path(physical_authority_value)
        if physical_authority_value
        else Path.home() / ".Xauthority"
    )
    if not physical_authority.is_file():
        physical_authority = None

    runtime_root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    bridge_runtime = runtime_root / "uu-remote-bridge"
    console_runtime = runtime_root / "uu-remote-console"
    private_display_file = bridge_runtime / "private-display"
    controller_display_file = bridge_runtime / "controller-display"
    authority = bridge_runtime / "Xauthority"
    if not private_display_file.is_file() or not authority.is_file():
        raise TraceError("The UU bridge private display is not running")
    private_display = private_display_file.read_text(encoding="utf-8").strip()
    controller_display = (
        controller_display_file.read_text(encoding="utf-8").strip()
        if controller_display_file.is_file()
        else private_display
    )
    if not DISPLAY_NAME.fullmatch(controller_display):
        raise TraceError("The UU controller display marker is invalid")

    physical_environment = xenv(physical_display, physical_authority)
    controller_environment = xenv(controller_display, authority)
    run(["/usr/bin/xdpyinfo"], env=physical_environment)
    run(["/usr/bin/xdpyinfo"], env=controller_environment)
    wanted_port = (
        (console_runtime / "window.port").read_text(encoding="utf-8").strip()
        if (console_runtime / "window.port").is_file()
        else None
    )
    process = find_controller_x11vnc(controller_display, wanted_port)
    state = query_x11vnc(process, controller_environment)
    capture_window = parse_window_id(state.get("id")) or parse_window_id(
        str(process.get("id") or "")
    )
    if not capture_window:
        raise TraceError("Could not identify x11vnc's current UU capture window")
    port = str(process.get("port") or "")
    viewer_pid = find_viewer_pid(port)
    viewer_window = find_viewer_window(viewer_pid, physical_environment)
    viewer_geometry = window_geometry(physical_environment, viewer_window)
    source_geometry = window_geometry(controller_environment, capture_window)
    controller_state_file = console_runtime / "controller.state"
    starting_controller_state = read_controller_state(controller_state_file)

    output = args.output or default_output()
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists():
        raise TraceError(f"Trace output already exists: {output}")

    started_at_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    collectors = [
        XInputCollector(
            layer="physical",
            environment=physical_environment,
            started=started,
            snapshot=target_classifier(
                physical_environment,
                expected_window=viewer_window,
                expected_class="viewer",
                expected_geometry=viewer_geometry,
                controller_state_file=controller_state_file,
            ),
        ),
        XInputCollector(
            layer="controller",
            environment=controller_environment,
            started=started,
            snapshot=target_classifier(
                controller_environment,
                expected_window=capture_window,
                expected_class="uu",
                expected_geometry=source_geometry,
                controller_state_file=controller_state_file,
            ),
        ),
    ]
    pollers = [
        PointerPoller(
            layer="physical",
            environment=physical_environment,
            geometry=viewer_geometry,
        ),
        PointerPoller(
            layer="controller",
            environment=controller_environment,
            geometry=source_geometry,
        ),
    ]
    print(
        f"Tracing for {args.duration} seconds. Use UU Remote normally: one harmless "
        "click, one harmless key, then switch once to a local app."
    )
    print("Key identities, text, window titles, clipboard data, and pixels are not recorded.")
    for collector in collectors:
        collector.start()
        if not collector.ready.wait(timeout=2):
            raise TraceError(f"The {collector.layer} XInput collector did not start")
    for poller in pollers:
        poller.start()
    try:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            time.sleep(min(0.2, deadline - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        for collector in collectors:
            collector.stop()
        for poller in pollers:
            poller.stop()
        for collector in collectors:
            collector.join(timeout=3)
        for poller in pollers:
            poller.join(timeout=3)

    errors = {
        worker.layer: worker.error
        for worker in [*collectors, *pollers]
        if worker.error
    }
    events = sorted(
        [event for collector in collectors for event in collector.events],
        key=lambda event: event.observed_ms,
    )
    motion = {poller.layer: poller.motion_count for poller in pollers}
    summary = summarize(events, motion)
    document = {
        "schema_version": 1,
        "privacy": {
            "records_key_identity": False,
            "records_text": False,
            "records_window_titles": False,
            "records_clipboard": False,
            "records_pixels": False,
        },
        "started_at": started_at_utc,
        "duration_seconds": args.duration,
        "topology": {
            "physical_display": physical_display,
            "controller_display": controller_display,
            "viewer_window": hex(viewer_window),
            "viewer_geometry": viewer_geometry,
            "source_window": hex(capture_window),
            "source_geometry": source_geometry,
            "x11vnc_pid": process["pid"],
            "x11vnc_port": port,
            "x11vnc_state": state,
            "controller_state_start": starting_controller_state,
            "controller_state_end": read_controller_state(controller_state_file),
        },
        "collector_errors": errors,
        "events": [asdict(event) for event in events],
        "summary": summary,
    }
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"Trace: {output}")
    print(json.dumps(summary, sort_keys=True))
    if errors:
        print(f"Collector errors: {errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TraceError as error:
        print(f"UU controller trace: {error}", file=sys.stderr)
        raise SystemExit(1)
