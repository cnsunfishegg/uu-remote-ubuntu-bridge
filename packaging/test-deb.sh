#!/usr/bin/env bash

set -Eeuo pipefail

asset="${1:?usage: packaging/test-deb.sh PACKAGE.deb}"
[[ -f "$asset" ]] || { printf 'Missing .deb: %s\n' "$asset" >&2; exit 2; }
package_name='uu-remote-ubuntu-bridge-installer'
[[ "$(dpkg-deb --field "$asset" Package)" == "$package_name" ]]
[[ "$(dpkg-deb --field "$asset" Architecture)" == amd64 ]]

temporary="$(mktemp -d -p /tmp uu-remote-deb-test.XXXXXXXX)"
cleanup() { rm -r -- "$temporary"; }
trap cleanup EXIT
mkdir -p "$temporary/root" "$temporary/control" "$temporary/home"
dpkg-deb --extract "$asset" "$temporary/root"
dpkg-deb --control "$asset" "$temporary/control"
if [[ -e "$temporary/control/postinst" ||
      -e "$temporary/control/prerm" ||
      -e "$temporary/control/postrm" ]]; then
    printf 'A Debian maintainer script would touch host state.\n' >&2
    exit 1
fi
source_root="$temporary/root/usr/share/$package_name"
[[ -x "$temporary/root/usr/bin/uu-remote-bridge-setup" ]]
[[ -f "$temporary/root/usr/share/applications/uu-remote.desktop" ]]
grep -q 'Exec=uu-remote-bridge-setup --from-desktop' \
    "$temporary/root/usr/share/applications/uu-remote.desktop"
[[ -f "$source_root/source/LICENSE" ]]
[[ -f "$temporary/root/usr/share/doc/$package_name/copyright" ]]
[[ -x "$source_root/source/install.sh" ]]
if find "$temporary/root" -type f \( \
    -iname '*.exe' -o -iname '*.dll' -o -iname '*.log' -o \
    -name 'setting_*.ini' \) -print -quit | grep -q .; then
    printf 'A binary, log, or account-state file entered the package.\n' >&2
    exit 1
fi

HOME="$temporary/home" \
XDG_DATA_HOME="$temporary/home/.local/share" \
UURB_PACKAGE_ROOT="$source_root" \
    "$temporary/root/usr/bin/uu-remote-bridge-setup" --help \
    >"$temporary/help.txt"
grep -q 'usage: ./install.sh' "$temporary/help.txt"
printf 'Debian package structure, contents, and setup help passed.\n'
