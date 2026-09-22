#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
package_name='uu-remote-ubuntu-bridge-installer'
version="${1:-$(<"$repo_dir/packaging/VERSION")}"
output_dir="${2:-$repo_dir/dist}"

if [[ ! "$version" =~ ^[0-9][A-Za-z0-9.+:~\-]*$ ]] ||
   ! dpkg --validate-version "$version" >/dev/null 2>&1; then
    printf 'Invalid Debian package version: %s\n' "$version" >&2
    exit 2
fi
if [[ "$output_dir" != /* ]]; then
    printf 'The output directory must be absolute.\n' >&2
    exit 2
fi
if [[ "$(dpkg --print-architecture)" != amd64 ]]; then
    printf 'This package is currently built for amd64 only.\n' >&2
    exit 1
fi
if [[ -n "$(git -C "$repo_dir" status --porcelain --untracked-files=all)" ]]; then
    printf 'Commit and review every source change before building the .deb.\n' >&2
    exit 1
fi

temporary="$(mktemp -d -p /tmp uu-remote-deb.XXXXXXXX)"
cleanup() { rm -r -- "$temporary"; }
trap cleanup EXIT
stage="$temporary/package"
package_root="$stage/usr/share/$package_name"
doc_root="$stage/usr/share/doc/$package_name"
mkdir -p "$stage/DEBIAN" "$stage/usr/bin" "$package_root/source" \
    "$doc_root" "$output_dir"

# The archive contains only tracked source from the exact committed revision.
# It excludes the ignored Wine prefix, downloads, build artifacts, and logs.
git -C "$repo_dir" archive --format=tar HEAD | \
    tar -xf - -C "$package_root/source"
install -m 0755 "$repo_dir/packaging/uu-remote-bridge-setup" \
    "$stage/usr/bin/uu-remote-bridge-setup"
install -m 0644 "$repo_dir/LICENSE" "$doc_root/copyright"
install -m 0644 "$repo_dir/packaging/README.Debian" "$doc_root/README.Debian"
printf '%s\n' "$version" >"$package_root/VERSION"
chmod 0644 "$package_root/VERSION"
sed "s/@VERSION@/$version/g" "$repo_dir/packaging/control.in" \
    >"$stage/DEBIAN/control"
chmod 0644 "$stage/DEBIAN/control"

# GitHub release assets normalize '~' in filenames. Keep the Debian control
# version intact, but use a portable filename for the downloadable artifact.
asset_version="${version//\~/-}"
asset="$output_dir/${package_name}_${asset_version}_amd64.deb"
dpkg-deb --root-owner-group --build "$stage" "$asset"
printf 'Built %s\n' "$asset"
(
    cd "$output_dir"
    sha256sum "$(basename -- "$asset")" >"$(basename -- "$asset").sha256"
)
cat "$asset.sha256"
