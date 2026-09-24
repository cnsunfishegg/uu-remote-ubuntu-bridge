"""Behavior checks for the privacy-safe outgoing-controller input trace."""

from dataclasses import asdict
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uu_controller_trace", ROOT / "scripts/uu_controller_trace.py"
)
assert SPEC and SPEC.loader
TRACE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TRACE
SPEC.loader.exec_module(TRACE)


BUTTON_BLOCK = """EVENT type 15 (RawButtonPress)
    device: 2 (4)
    time: 67159650
    detail: 1
""".splitlines()

KEY_BLOCK = """EVENT type 13 (RawKeyPress)
    device: 3 (5)
    time: 67159750
    detail: 38
""".splitlines()


class ControllerTraceTests(unittest.TestCase):
    def event(self, block, *, layer, at, target):
        return TRACE.parse_event_block(
            block,
            layer=layer,
            observed_ms=at,
            pointer_master=2,
            keyboard_master=3,
            snapshot=lambda *_: (target, 0x200001, 100.0, 120.0, 7),
        )

    def test_key_identity_is_discarded_but_delivery_boundary_is_kept(self):
        event = self.event(KEY_BLOCK, layer="physical", at=100, target="viewer")
        self.assertIsNotNone(event)
        record = asdict(event)
        self.assertNotIn("detail", record)
        self.assertNotIn("key", record)
        self.assertIsNone(record["button"])
        self.assertEqual(record["target"], "viewer")
        self.assertEqual(record["kind"], "KeyPress")
        self.assertEqual(record["generation"], 7)

    def test_matching_outer_and_inner_events_prove_only_private_delivery(self):
        outer_button = self.event(
            BUTTON_BLOCK, layer="physical", at=100, target="viewer"
        )
        inner_button = self.event(
            BUTTON_BLOCK, layer="controller", at=160, target="uu"
        )
        outer_key = self.event(KEY_BLOCK, layer="physical", at=300, target="viewer")
        inner_key = self.event(KEY_BLOCK, layer="controller", at=360, target="uu")
        summary = TRACE.summarize(
            [outer_button, inner_button, outer_key, inner_key],
            {"physical": 4, "controller": 3},
        )
        self.assertEqual(summary["paired_button_presses"], 1)
        self.assertEqual(summary["paired_key_presses"], 1)
        self.assertEqual(summary["verdict"], "input_reached_private_uu_window")
        self.assertTrue(summary["remote_target_observation_required"])

    def test_missing_private_event_names_the_local_boundary(self):
        outer = self.event(BUTTON_BLOCK, layer="physical", at=100, target="viewer")
        summary = TRACE.summarize([outer], {"physical": 1, "controller": 0})
        self.assertEqual(
            summary["verdict"], "viewer_received_button_but_private_uu_did_not"
        )

    def test_pointer_motion_names_the_first_stalled_boundary(self):
        summary = TRACE.summarize([], {"physical": 3, "controller": 0})
        self.assertEqual(
            summary["verdict"], "viewer_pointer_moved_but_private_pointer_did_not"
        )
        forwarded = TRACE.summarize([], {"physical": 3, "controller": 2})
        self.assertEqual(
            forwarded["verdict"], "pointer_motion_reached_private_display"
        )

    def test_local_key_followed_by_private_key_flags_possible_focus_leak(self):
        local = self.event(KEY_BLOCK, layer="physical", at=100, target="other")
        private = self.event(KEY_BLOCK, layer="controller", at=180, target="uu")
        summary = TRACE.summarize([local, private], {})
        self.assertEqual(summary["possible_focus_leaks"], 1)
        self.assertEqual(summary["verdict"], "focus_leak_suspected")

    @unittest.skipUnless(
        all(shutil.which(command) for command in ("Xvfb", "xinput", "xdotool")),
        "isolated XInput dependencies are unavailable",
    )
    def test_collector_observes_real_xinput_without_key_identity(self):
        with tempfile.TemporaryDirectory(prefix="uu-controller-trace-") as temporary:
            display_number = Path(temporary) / "display-number"
            with display_number.open("w+") as descriptor:
                xvfb = subprocess.Popen(
                    [
                        "Xvfb",
                        "-displayfd",
                        str(descriptor.fileno()),
                        "-screen",
                        "0",
                        "800x600x24",
                        "-nolisten",
                        "tcp",
                        "-ac",
                    ],
                    pass_fds=(descriptor.fileno(),),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    number = ""
                    for _ in range(30):
                        descriptor.seek(0)
                        number = descriptor.read().strip()
                        if number:
                            break
                        time.sleep(0.05)
                    self.assertTrue(number, "Xvfb did not choose a display")
                    environment = dict(os.environ, DISPLAY=f":{number}")
                    environment.pop("XAUTHORITY", None)
                    started = time.monotonic()
                    collector = TRACE.XInputCollector(
                        layer="controller",
                        environment=environment,
                        started=started,
                        snapshot=lambda *_: ("uu", 0x3A7, 100.0, 120.0, 3),
                    )
                    collector.start()
                    self.assertTrue(collector.ready.wait(timeout=2))
                    time.sleep(0.15)
                    subprocess.run(
                        ["xdotool", "mousemove", "100", "120", "click", "1", "key", "a"],
                        env=environment,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(0.25)
                    collector.stop()
                    collector.join(timeout=3)
                    self.assertIsNone(collector.error)
                    kinds = [event.kind for event in collector.events]
                    self.assertIn("ButtonPress", kinds)
                    self.assertIn("ButtonRelease", kinds)
                    self.assertIn("KeyPress", kinds)
                    self.assertIn("KeyRelease", kinds)
                    key = next(event for event in collector.events if event.kind == "KeyPress")
                    self.assertIsNone(key.button)
                    locations = [(100.0, 120.0, 1), (100.0, 120.0, 1),
                                 (200.0, 220.0, 1), (200.0, 220.0, 1)]
                    calls = 0

                    def changing_pointer(_environment):
                        nonlocal calls
                        value = locations[min(calls, len(locations) - 1)]
                        calls += 1
                        return value

                    with mock.patch.object(
                        TRACE, "pointer_location", side_effect=changing_pointer
                    ):
                        poller = TRACE.PointerPoller(
                            layer="controller", environment=environment
                        )
                        poller.start()
                        time.sleep(0.25)
                        poller.stop()
                        poller.join(timeout=2)
                    self.assertGreater(poller.motion_count, 0, poller.error)
                finally:
                    xvfb.terminate()
                    try:
                        xvfb.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        xvfb.kill()
                        xvfb.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
