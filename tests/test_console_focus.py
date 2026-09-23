"""Exercise console focus helpers with fake X commands, never a live desktop."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "scripts/uu-remote-console").read_text()


class ConsoleFocusTests(unittest.TestCase):
    def test_local_window_keeps_bidirectional_input_on_loopback(self):
        window = SOURCE.split("open_window() {", 1)[1].split("serve_console() {", 1)[0]
        self.assertIn('-display "$bridge_display"', window)
        self.assertNotIn('-sid "$client_window"', window)
        self.assertNotIn('        -id "$client_window"', window)
        self.assertIn('-listen 127.0.0.1', window)
        self.assertIn('-localhost', window)
        self.assertNotIn('-viewonly', window)
        self.assertNotIn('-nomouse', window)
        self.assertNotIn('-nokeyboard', window)
        self.assertIn('-geometry "${client_width}x${client_height}"', window)
        self.assertIn('-clip "$initial_clip"', window)
        self.assertIn('monitor_private_scene "$initial_clip" &', window)
        self.assertIn('X11VNC_REMOTE=$window_remote_channel', window)
        self.assertIn('-R "clip:$clip"', SOURCE)
        self.assertIn('-gone "$script_path release-client"', window)
        self.assertNotIn('-R "sid:', window)
        self.assertIn('stop_window_child "$window_vnc_pid"', SOURCE)
        self.assertIn('/usr/bin/flock -w 4 9', window)

    def run_helpers(self, mode, commands):
        with tempfile.TemporaryDirectory(prefix="uu-focus-test-") as temp:
            directory = Path(temp)
            xdo = directory / "xdotool"
            xdo.write_text('''#!/usr/bin/env bash
case "$*" in
  *search*gameviewer*) printf '100\\n200\\n300\\n';;
  *getactivewindow*)
    [[ "$FOCUS_TEST_MODE" == active_small ]] && printf '100\\n';;
  *getwindowname*100*) printf '网易UU远程\\n';;
  *getwindowname*200*) printf 'Remote session\\n';;
  *getwindowname*300*) printf 'GameViewer\\n';;
  *getwindowname*202*) printf 'UU Remote - TigerVNC\\n';;
  *getwindowname*203*) printf 'xbt:0 - TigerVNC\\n';;
  *getwindowgeometry*100*) printf '  Geometry: 920x680\\n';;
  *getwindowgeometry*200*) printf '  Geometry: 1536x904\\n';;
  *getwindowgeometry*300*) printf '  Geometry: 96x136\\n';;
  *search*Ubuntu-Desktop-Relay*)
    [[ "$FOCUS_TEST_MODE" == rdp ]] || exit 1
    printf '101\\n';;
  *search*TigerVNC*|*search*realvnc-vncviewer*)
    [[ "$FOCUS_TEST_MODE" == vnc ]] || exit 1
    printf '202\\n203\\n';;
  *) printf '%s\\n' "$*" >> "$FOCUS_TEST_LOG";;
esac
''')
            xprop = directory / "xprop"
            xprop.write_text('''#!/usr/bin/env bash
if [[ "$*" == *100* && "$FOCUS_TEST_MODE" != active_small ]]; then
    printf 'WM_STATE(WM_STATE): window state: Iconic\\n'
elif [[ "$*" == *200* || "$*" == *300* ||
        ( "$*" == *100* && "$FOCUS_TEST_MODE" == active_small ) ]]; then
    printf 'WM_STATE(WM_STATE): window state: Normal\\n'
else
    printf 'WM_STATE: not found.\\n'
fi
''')
            wmctrl = directory / "wmctrl"
            wmctrl.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FOCUS_TEST_LOG"
''')
            xdo.chmod(0o700)
            xprop.chmod(0o700)
            wmctrl.chmod(0o700)
            # Source only definitions, substitute private fake X executables,
            # and override discovery so the real X server is never used.
            script = SOURCE.split('case "${1:-open}" in', 1)[0]
            script = (script.replace("/usr/bin/xdotool", str(xdo))
                            .replace("/usr/bin/xprop", str(xprop))
                            .replace("/usr/bin/wmctrl", str(wmctrl)))
            script += '\ndiscover_bridge() { bridge_display=:99; bridge_xauthority=/none; }\n'
            script += commands
            env = dict(os.environ, HOME=temp, DISPLAY=":99", XDG_RUNTIME_DIR=temp, XDG_STATE_HOME=temp,
                       FOCUS_TEST_MODE=mode, FOCUS_TEST_LOG=str(directory / "calls"))
            result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
            calls = (directory / "calls").read_text() if (directory / "calls").exists() else ""
            return result, calls, (directory / "uu-remote-bridge/console-focus").exists()

    def test_restores_rdp(self):
        result, calls, lease = self.run_helpers("rdp", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowminimize 101", calls)
        self.assertIn("windowmap 101 windowactivate 101", calls)
        self.assertFalse(lease)

    def test_restores_native_vnc_and_filters_toast(self):
        result, calls, lease = self.run_helpers("vnc", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowmap 200 windowactivate --sync 200", calls)
        self.assertNotIn("windowmap 100", calls)
        self.assertNotIn("windowmap 300", calls)
        self.assertIn("windowminimize 203", calls)
        self.assertIn("windowmap 203 windowactivate 203", calls)
        self.assertFalse(lease)

    def test_missing_relay_still_releases_lease(self):
        result, calls, lease = self.run_helpers("none", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("windowactivate 101", calls)
        self.assertNotIn("windowactivate 202", calls)
        self.assertFalse(lease)

    def test_selects_visible_large_window_over_iconified_shell(self):
        result, _, _ = self.run_helpers("none", "find_client_window")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "200")

    def test_selects_active_session_window_over_larger_background_window(self):
        result, _, _ = self.run_helpers("active_small", "find_client_window")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "100")

    def test_stuck_viewer_child_does_not_hold_window_lock_forever(self):
        started = time.monotonic()
        result, _, _ = self.run_helpers(
            "none",
            """python3 -c 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)' &
stuck=$!
sleep 0.2
stop_window_child "$stuck"
if kill -0 "$stuck" 2>/dev/null; then exit 1; fi
""",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - started, 4)

    def test_fullscreen_state_targets_only_the_local_uu_viewer(self):
        result, calls, _ = self.run_helpers(
            "vnc", "set_local_viewer_fullscreen add"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-ir 0xca -b add,fullscreen", calls)


if __name__ == "__main__":
    unittest.main()
