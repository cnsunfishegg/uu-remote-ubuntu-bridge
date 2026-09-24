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
        self.assertIn('-id "$client_window"', window)
        self.assertIn('-listen 127.0.0.1', window)
        self.assertIn('-localhost', window)
        self.assertNotIn('-viewonly', window)
        self.assertNotIn('-nomouse', window)
        self.assertNotIn('-nokeyboard', window)
        self.assertIn('-geometry "${client_width}x${client_height}"', window)
        self.assertIn('-ViewOnly=0', window)
        self.assertIn('-FullScreen="$controller_fullscreen_value"', window)
        self.assertIn('-FullscreenSystemKeys=1', window)
        self.assertIn('-MenuKey=F8', window)
        self.assertIn('-AlwaysCursor=1', window)
        self.assertIn('-CursorType=System', window)
        self.assertIn('-PointerEventInterval=8', window)
        self.assertIn('-PreferredEncoding=Raw', window)
        self.assertIn('-input KMBC', window)
        self.assertIn('-always_inject', window)
        self.assertIn('-wait 10', window)
        self.assertIn('-defer 0', window)
        self.assertIn('-nowait_bog', window)
        self.assertNotIn('move_local_viewer_by "$viewer_window"', SOURCE)
        self.assertIn('private_window_geometry "$candidate"', SOURCE)
        self.assertIn('/usr/bin/xwininfo -id "$1" -stats', SOURCE)
        self.assertNotIn('set_private_window_maximized "$candidate"', SOURCE)
        self.assertNotIn('-clip "$initial_clip"', window)
        self.assertIn('-xwarppointer', window)
        self.assertIn('monitor_private_scene "$client_window" \\', window)
        self.assertIn('"$presentation_width" "$presentation_height" \\', window)
        self.assertIn(
            '"$presentation_mode" "$initial_capture_signature" \\', window
        )
        self.assertIn('"$initial_scale" 9>&- &', window)
        self.assertIn('find_remote_scene_candidate()', SOURCE)
        self.assertIn('maximize_private_remote_scene()', SOURCE)
        self.assertIn('if maximize_private_remote_scene "$fast_remote"', SOURCE)
        self.assertIn('x11vnc_capture_args+=(-scale "$initial_scale")', window)
        self.assertIn('initial_capture_signature="root-clip:$client_window:', window)
        self.assertIn('-clip "${client_width}x${client_height}+${client_x}+${client_y}"', window)
        self.assertIn('X11VNC_REMOTE=$window_remote_channel', window)
        self.assertIn('desired_capture="id:$candidate"', SOURCE)
        self.assertIn('capture_mode=sid', SOURCE)
        self.assertIn('capture_command="script:sid:$candidate;refresh"', SOURCE)
        self.assertIn('capture_mode=root-clip', SOURCE)
        self.assertIn('capture_command="script:clip:${width}x${height}+${x}+${y};refresh"', SOURCE)
        self.assertIn('find_private_overlay "$candidate"', SOURCE)
        self.assertIn("shape_fullscreen_dialog_overlay()", SOURCE)
        self.assertIn("XShapeCombineRectangles", SOURCE)
        self.assertIn("for shape_kind in (0, 2)", SOURCE)
        self.assertIn(
            'shape_fullscreen_dialog_overlay "$candidate"', SOURCE
        )
        self.assertIn("'_NET_WM_WINDOW_TYPE_DIALOG'", SOURCE)
        self.assertIn('-R "$capture_command"', SOURCE)
        self.assertIn('-gone "$script_path release-client"', window)
        self.assertIn('>>"$state_dir/window-x11vnc.log" 2>&1 9>&- &', window)
        self.assertIn('>>"$state_dir/window-viewer.log" 2>&1 9>&-', window)
        self.assertIn('stop_window_child "$window_vnc_pid"', SOURCE)
        self.assertIn('publish_controller_state "$state_generation" ready', SOURCE)
        self.assertIn(
            'rm -f "$runtime_dir/window.port" "$controller_state_file"', SOURCE
        )
        self.assertIn('/usr/bin/flock -w 4 9', window)
        self.assertIn('controller_fullscreen="${UURB_CONTROLLER_FULLSCREEN:-auto}"', SOURCE)
        self.assertIn('controller_remote_session_active', window)
        self.assertIn('request_presentation_mode "$desired_presentation"', SOURCE)
        self.assertIn('set_local_viewer_borderless "$viewer_window"', SOURCE)
        self.assertIn(
            'windowactivate --sync "$viewer_window"', SOURCE
        )
        self.assertIn("focus_local_viewer_when_mapped()", SOURCE)
        self.assertIn(
            'focus_local_viewer_when_mapped "$presentation_mode"', SOURCE
        )
        self.assertIn('sleep 0.02', SOURCE)
        self.assertIn('stop_window_child "$window_focus_pid"', SOURCE)
        self.assertIn('stop_window_child "$window_drag_pid"', SOURCE)
        self.assertIn("enable_local_viewer_drag_when_mapped()", SOURCE)
        self.assertIn(
            'enable_local_viewer_drag_when_mapped "$presentation_mode"',
            window,
        )
        self.assertIn(
            '[[ "$controller_fullscreen" == auto && "$mode" == windowed ]]',
            SOURCE,
        )
        self.assertIn("InputOnly = 2", SOURCE)
        self.assertIn("ButtonMotionMask = 1 << 13", SOURCE)
        self.assertIn("x11.XMoveWindow(", SOURCE)
        self.assertIn('if [[ -z "$viewer_window" ]]', SOURCE)
        self.assertNotIn(
            'if [[ "$presentation_fullscreen" == false && -z "$viewer_window" ]]',
            SOURCE,
        )
        self.assertIn('exec "$script_path" window', window)
        self.assertIn('restart uu-remote-bridge.service', window)
        self.assertLess(
            window.index('cleanup_window\n        exec 9>&-'),
            window.index('restart uu-remote-bridge.service'),
        )

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
  *getwindowgeometry*202*) printf 'WIDTH=1150\\nHEIGHT=790\\n';;
  *search*Ubuntu-Desktop-Relay*)
    [[ "$FOCUS_TEST_MODE" == rdp ]] || exit 1
    printf '101\\n';;
  *search*TigerVNC*|*search*realvnc-vncviewer*)
    [[ "$FOCUS_TEST_MODE" == vnc ]] || exit 1
    printf '202\\n203\\n';;
  *windowmap*200*)
    [[ "$DISPLAY" == :99 && "$XAUTHORITY" == /none ]] || exit 9
    printf '%s\\n' "$*" >> "$FOCUS_TEST_LOG";;
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

    def test_isolated_controller_never_minimizes_or_leases_host(self):
        result, calls, lease = self.run_helpers("vnc", '''
mkdir -p "$bridge_runtime_dir"
printf ':99.1\\n' >"$controller_display_file"
display_ready() { [[ "$1" == :99.1 ]]; }
focus_client
release_client
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lease)
        self.assertNotIn("windowminimize", calls)
        self.assertNotIn("windowactivate 203", calls)

    def test_invalid_controller_display_fails_closed(self):
        result, _, lease = self.run_helpers("none", '''
mkdir -p "$bridge_runtime_dir"
printf ':0\\n' >"$controller_display_file"
display_ready() { return 0; }
discover_controller
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(lease)

    def test_selects_visible_large_window_over_iconified_shell(self):
        result, _, _ = self.run_helpers("none", "find_client_window")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "200")

    def test_selects_active_session_window_over_larger_background_window(self):
        for helper in ("find_client_window", "find_scene_window"):
            with self.subTest(helper=helper):
                result, _, _ = self.run_helpers("active_small", helper)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "100")

    def test_primary_scene_helpers_reject_transient_dialogs(self):
        for helper in ("find_client_window", "find_scene_window"):
            body = SOURCE.split(f"{helper}() {{", 1)[1].split("\n}\n", 1)[0]
            with self.subTest(helper=helper):
                self.assertIn("_NET_WM_WINDOW_TYPE_DIALOG", body)
                self.assertIn("WM_TRANSIENT_FOR(WINDOW)", body)

    def test_detects_only_a_visible_remote_scene_as_active_session(self):
        result, _, _ = self.run_helpers(
            "none", "controller_remote_session_active"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _, _ = self.run_helpers(
            "active_small", "controller_remote_session_active"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_detects_launcher_as_the_active_scene_after_session_exit(self):
        result, _, _ = self.run_helpers(
            "active_small", "controller_management_scene_active"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _, _ = self.run_helpers(
            "none", "controller_management_scene_active"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_auto_presentation_separates_launcher_and_remote_canvas(self):
        cases = (
            ("presentation_mode_for_scene 100 100 1920 1080 true", "windowed"),
            ("presentation_mode_for_scene 200 100 1920 1080 true", "fullscreen"),
            ("presentation_mode_for_scene 200 100 1536 904 false", "fullscreen"),
            # A small UU bootstrap canvas must never be enlarged as if it
            # were the final desktop. The monitor first maximizes the real
            # private window; only that screen-sized canvas goes full-screen.
            ("presentation_mode_for_scene 200 100 640 360 false", "windowed"),
            ("presentation_mode_for_scene 300 100 700 500 false", "windowed"),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                result, _, _ = self.run_helpers("none", command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

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

    def test_completed_window_child_is_reaped_without_full_timeout(self):
        self.assertIn('process_state="${stat_line##*) }"', SOURCE)
        self.assertIn(
            '[[ "$process_state" == Z || "$process_state" == X ]] && break',
            SOURCE,
        )

    def test_private_client_does_not_inherit_outer_window_lock(self):
        with tempfile.TemporaryDirectory(prefix="uu-lock-inheritance-") as temp:
            root = Path(temp)
            helper = root / ".local/bin/uu-remote"
            helper.parent.mkdir(parents=True)
            helper.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ -e /proc/self/fd/9 ]]; then\n"
                "  printf inherited >\"$HOME/fd-result\"\n"
                "  exit 9\n"
                "fi\n"
                "printf closed >\"$HOME/fd-result\"\n"
            )
            helper.chmod(0o700)
            script = SOURCE.split('case "${1:-open}" in', 1)[0]
            script += '''
mkdir -p "$state_dir"
exec 9>"$HOME/window.lock"
flock 9
wake_private_client
'''
            env = dict(
                os.environ,
                HOME=temp,
                XDG_RUNTIME_DIR=temp,
                XDG_STATE_HOME=temp,
            )
            result = subprocess.run(
                ["bash", "-c", script], env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "fd-result").read_text(), "closed")

    def test_reopening_iconified_viewer_restores_both_window_layers(self):
        result, calls, _ = self.run_helpers("vnc", "activate_existing_window")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowmap 200 windowactivate --sync 200", calls)
        self.assertIn("windowmap 202 windowactivate --sync 202", calls)
        self.assertLess(
            calls.index("windowmap 200 windowactivate --sync 200"),
            calls.index("windowmap 202 windowactivate --sync 202"),
        )

    def test_fit_scale_preserves_aspect_and_stays_inside_viewport(self):
        for width, height in ((920, 680), (1920, 1080), (2560, 1600)):
            with self.subTest(source=(width, height)):
                result, _, _ = self.run_helpers(
                    "vnc", f"viewer_fit_scale {width} {height}"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                scale = float(result.stdout)
                self.assertGreater(scale, 0)
                self.assertLessEqual(width * scale, 1148)
                self.assertLessEqual(height * scale, 790)
                self.assertLess(min(1148 / width, 790 / height) - scale, 0.000002)


if __name__ == "__main__":
    unittest.main()
