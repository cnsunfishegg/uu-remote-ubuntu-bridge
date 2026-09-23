"""Check duplicate desktop shortcuts are archived, not deleted."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


INSTALLER = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
ARCHIVE_BLOCK = INSTALLER.split(
    "# Keep one obvious desktop entry.", 1
)[1].split("\n", 1)[1].split('\nif [[ "$start_service" == true ]]', 1)[0]


class DesktopShortcutTests(unittest.TestCase):
    def run_archive(self, wine_matches: bool) -> tuple[list[str], list[str]]:
        with tempfile.TemporaryDirectory(prefix="uu-shortcut-test-") as folder:
            home = Path(folder)
            desktop = home / "Desktop"
            desktop.mkdir()
            applications = home / ".local/share/applications/wine/Programs"
            applications.mkdir(parents=True)
            prefix = home / "wine-prefix"
            controller = desktop / "UU Remote Controller.desktop"
            controller.write_text(
                f"Exec={home}/.local/bin/uu-remote control\n"
            )
            direct = desktop / "UU远程.desktop"
            menu = applications / "UU远程.desktop"
            listed_prefix = prefix if wine_matches else home / "other-prefix"
            direct.write_text(
                f'Exec=env "WINEPREFIX={listed_prefix}" wine GameViewer.exe\n'
            )
            menu.write_text(
                f'Exec=env "WINEPREFIX={listed_prefix}" wine UU远程.lnk\n'
            )
            protocol = home / ".local/share/applications/wine-protocol-uuremote.desktop"
            protocol.parent.mkdir(parents=True, exist_ok=True)
            protocol.write_text(
                f'Exec=env "WINEPREFIX={listed_prefix}" wine start %u\n'
                'MimeType=x-scheme-handler/uuremote;\n'
            )
            primary = desktop / "UU Remote.desktop"
            primary.write_text("Exec=uu-remote open\n")
            environment = os.environ | {
                "HOME": str(home),
                "UURB_TEST_PREFIX": str(prefix),
            }
            command = 'wine_prefix="$UURB_TEST_PREFIX"\n' + ARCHIVE_BLOCK
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", command],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = home / ".local/share/uu-remote-bridge/old-shortcuts"
            archived = sorted(
                path.name for path in archive.glob("set-*/*")
            ) if archive.exists() else []
            remaining = sorted(
                str(path.relative_to(home))
                for path in (controller, direct, menu, protocol, primary)
                if path.exists()
            )
            return archived, remaining

    def test_archives_only_matching_old_launchers(self):
        archived, remaining = self.run_archive(wine_matches=True)
        self.assertEqual(
            archived,
            [
                "UU Remote Controller.desktop",
                "UU远程.desktop",
                "menu-UU远程.desktop",
                "wine-protocol-uuremote.desktop",
            ],
        )
        self.assertEqual(remaining, ["Desktop/UU Remote.desktop"])

    def test_preserves_unrelated_wine_shortcuts(self):
        archived, remaining = self.run_archive(wine_matches=False)
        self.assertEqual(
            archived,
            ["UU Remote Controller.desktop", "wine-protocol-uuremote.desktop"],
        )
        self.assertEqual(
            remaining,
            [
                ".local/share/applications/wine/Programs/UU远程.desktop",
                "Desktop/UU Remote.desktop",
                "Desktop/UU远程.desktop",
            ],
        )


if __name__ == "__main__":
    unittest.main()
