"""Behavior checks for the source-only Debian installer bundle."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
WRAPPER = REPOSITORY / "packaging" / "uu-remote-bridge-setup"


class DebianBundleTests(unittest.TestCase):
    def test_wrapper_copies_source_and_runs_only_when_asked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            source = bundle / "source"
            source.mkdir(parents=True)
            version = (REPOSITORY / "packaging" / "VERSION").read_text().strip()
            (bundle / "VERSION").write_text(version + "\n", encoding="ascii")
            marker = root / "marker"
            for filename, label in (("install.sh", "setup"), ("uninstall.sh", "remove")):
                script = source / filename
                script.write_text(
                    "#!/usr/bin/env bash\n"
                    f"printf '{label}:%s\\n' \"$*\" >'{marker}'\n",
                    encoding="ascii",
                )
                script.chmod(0o755)
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "XDG_DATA_HOME": str(root / "data"),
                "UURB_PACKAGE_ROOT": str(bundle),
            }
            blocked = subprocess.run(
                ["bash", str(WRAPPER), "--automatic-updates"],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("require a Git checkout", blocked.stderr)
            self.assertFalse(marker.exists())

            subprocess.run(
                ["bash", str(WRAPPER), "--help"], env=environment, check=True
            )
            self.assertEqual("setup:--help\n", marker.read_text(encoding="ascii"))
            copied = root / "data" / "uu-remote-ubuntu-bridge-installer" / version
            self.assertTrue((copied / ".package-ready").is_file())

            subprocess.run(
                ["bash", str(WRAPPER), "--from-desktop"],
                env=environment,
                input="\n",
                text=True,
                check=True,
            )
            self.assertEqual("setup:\n", marker.read_text(encoding="ascii"))

            subprocess.run(
                ["bash", str(WRAPPER), "--uninstall", "--dry-run"],
                env=environment,
                check=True,
            )
            self.assertEqual("remove:--dry-run\n", marker.read_text(encoding="ascii"))

    def test_control_and_installer_keep_first_run_explicit(self) -> None:
        control = (REPOSITORY / "packaging" / "control.in").read_text()
        builder = (REPOSITORY / "packaging" / "build-deb.sh").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        self.assertIn("Architecture: amd64", control)
        self.assertIn("Lachlan Chen", control)
        self.assertIn("git -C \"$repo_dir\" archive --format=tar HEAD", builder)
        self.assertIn('asset_version="${version//\\~/-}"', builder)
        self.assertNotIn("postinst", builder)
        menu_entry = (REPOSITORY / "packaging" / "uu-remote.desktop").read_text()
        self.assertIn("Exec=uu-remote-bridge-setup --from-desktop", menu_entry)
        self.assertIn("Terminal=true", menu_entry)
        self.assertIn('"$stage/usr/share/applications/uu-remote.desktop"', builder)
        self.assertIn('if [[ "$skip_packages" == true ]]', installer)
        self.assertIn("install_winehq", installer)


if __name__ == "__main__":
    unittest.main()
