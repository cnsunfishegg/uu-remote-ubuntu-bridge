#!/usr/bin/env bash

# Shared host policy for the installer and its test suite.  Keep the release
# choice narrow: a new Ubuntu release can change the GNOME Remote Desktop and
# libei ABI even when package names remain the same.

uurb_select_platform() {
    local distribution="${1:-}"
    local version="${2:-}"

    UURB_PLATFORM=''
    UURB_LIBEI_MODE=''

    case "$distribution:$version" in
        ubuntu:24.04)
            UURB_PLATFORM='ubuntu-24.04'
            # GNOME 46 is linked against the old distribution libei.  Use the
            # bridge-local, reviewed FD-leak backport for this one release.
            UURB_LIBEI_MODE='backport'
            ;;
        ubuntu:26.04)
            UURB_PLATFORM='ubuntu-26.04'
            # GNOME Remote Desktop 50 requires libei >= 1.3.901.  Its Ubuntu
            # 26.04 libei 1.5.0 already includes the upstream keymap-FD fix,
            # so an old ABI-compatible-looking 1.2.1 override is unsafe.
            UURB_LIBEI_MODE='system'
            ;;
        *)
            return 1
            ;;
    esac
}

uurb_require_system_libei() {
    local package_version

    if [[ ! -x /usr/bin/dpkg-query || ! -x /usr/bin/dpkg ]]; then
        printf 'Ubuntu 26.04 support requires dpkg-query and dpkg.\n' >&2
        return 1
    fi
    package_version="$(
        /usr/bin/dpkg-query -W -f='${Version}' libei1 2>/dev/null || true
    )"
    if [[ -z "$package_version" ]] || \
       ! /usr/bin/dpkg --compare-versions "$package_version" ge 1.5.0; then
        printf 'Ubuntu 26.04 requires libei1 1.5.0 or newer; found %s.\n' \
            "${package_version:-not installed}" >&2
        return 1
    fi
    UURB_SYSTEM_LIBEI_VERSION="$package_version"
}
