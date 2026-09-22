#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${UURB_BUILD_DIR:-$repo_dir/build/winpr}"
output_dir="${1:-$repo_dir/build/freerdp}"
downloads="$work_dir/downloads"
runtime="$work_dir/runtime"
source_dir="$work_dir/FreeRDP"
build_dir="$work_dir/build"
build_recipe="$output_dir/.build-recipe"
build_checksums="$output_dir/.build-sha256"

# Build the Windows SDL client and WinPR from one fixed FreeRDP revision.
# Nightly Jenkins binaries are deliberately not used because old jobs are
# pruned. SDL's versioned GitHub release assets are retained and hash-checked.
freerdp_commit='168925dac792142f6d0b66e7e2d568a3d439521c'
sdl_url='https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-devel-3.4.16-mingw.tar.gz'
sdl_sha256='c7ef65bd72eabac6e5b535411dbd8d5824d0aab24fd62ff8812666b336f18a9c'
sdl_ttf_url='https://github.com/libsdl-org/SDL_ttf/releases/download/release-3.2.2/SDL3_ttf-devel-3.2.2-mingw.tar.gz'
sdl_ttf_sha256='bb57f26787d6a2e108158562feb061fcdf6f68a110f9c8cf9af42ff343d4e41c'
openssl_url='https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-openssl-3.6.3-1-any.pkg.tar.zst'
openssl_sha256='82de7ff886112374ffae9e7b3c843c82342e198543fb024790416ef56434fe9f'
cjson_url='https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-cjson-1.7.19-1-any.pkg.tar.zst'
cjson_sha256='f20c3fa89ab072caba93baca374f40b8c9ce23d6383aa55552ff13f31c7879aa'
uriparser_url='https://repo.msys2.org/mingw/mingw64/mingw-w64-x86_64-uriparser-1.0.2-1-any.pkg.tar.zst'
uriparser_sha256='c7c1db089f04aa3c616fb53cddfa250b4e4dbb864b7d4d5250ade83e8a1e8d19'

require() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'missing build tool: %s\n' "$1" >&2
        exit 1
    }
}

download() {
    local url="$1"
    local expected="$2"
    local destination="$3"
    local attempt

    if [[ -f "$destination" ]] && \
       printf '%s  %s\n' "$expected" "$destination" | sha256sum -c - \
           >/dev/null 2>&1; then
        return
    fi
    for attempt in 1 2; do
        if command -v aria2c >/dev/null 2>&1; then
            aria2c --allow-overwrite=true --auto-file-renaming=false \
                --continue=true --max-connection-per-server=8 \
                --min-split-size=1M --split=8 \
                --dir="$(dirname -- "$destination")" \
                --out="$(basename -- "$destination").part" "$url"
        else
            curl --continue-at - --fail --location --retry 3 \
                --output "$destination.part" "$url"
        fi
        if printf '%s  %s\n' "$expected" "$destination.part" | \
            sha256sum -c -; then
            mv "$destination.part" "$destination"
            rm -f "$destination.part.aria2"
            return
        fi
        rm -f "$destination.part" "$destination.part.aria2"
        printf 'download hash mismatch; retrying %s (%s/2)\n' \
            "$url" "$attempt" >&2
    done
    printf 'download verification failed: %s\n' "$url" >&2
    exit 1
}

for command in cmake curl git ninja sha256sum tar \
    x86_64-w64-mingw32-gcc-win32 x86_64-w64-mingw32-g++-win32 \
    x86_64-w64-mingw32-windres; do
    require "$command"
done

mkdir -p "$downloads" "$(dirname -- "$output_dir")"
toolchain_sha256="$(sha256sum "$repo_dir/cmake/mingw-uurb-toolchain.cmake" | awk '{print $1}')"
script_sha256="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
recipe_id="$freerdp_commit:$toolchain_sha256:$script_sha256"
if [[ -f "$build_recipe" && -f "$build_checksums" ]] && \
   [[ "$(<"$build_recipe")" == "$recipe_id" ]] && \
   (cd "$output_dir" && sha256sum -c .build-sha256 >/dev/null 2>&1); then
    printf 'FreeRDP Windows relay runtime is already current in %s\n' \
        "$output_dir"
    exit 0
fi

download "$sdl_url" "$sdl_sha256" "$downloads/sdl3-devel.tar.gz"
download "$sdl_ttf_url" "$sdl_ttf_sha256" \
    "$downloads/sdl3-ttf-devel.tar.gz"
download "$openssl_url" "$openssl_sha256" "$downloads/openssl.pkg.tar.zst"
download "$cjson_url" "$cjson_sha256" "$downloads/cjson.pkg.tar.zst"
download "$uriparser_url" "$uriparser_sha256" \
    "$downloads/uriparser.pkg.tar.zst"

rm -rf "$runtime"
mkdir -p "$runtime"
for package in "$downloads"/*.pkg.tar.zst; do
    tar --zstd -xf "$package" -C "$runtime"
done
tar -xzf "$downloads/sdl3-devel.tar.gz" -C "$runtime"
tar -xzf "$downloads/sdl3-ttf-devel.tar.gz" -C "$runtime"

if [[ ! -d "$source_dir/.git" ]]; then
    rm -rf "$source_dir"
    git clone --filter=blob:none --no-checkout \
        https://github.com/FreeRDP/FreeRDP.git "$source_dir"
fi
git -C "$source_dir" fetch --depth 1 origin "$freerdp_commit"
git -C "$source_dir" checkout --detach "$freerdp_commit"
if [[ "$(git -C "$source_dir" rev-parse HEAD)" != "$freerdp_commit" ]]; then
    printf 'FreeRDP source revision verification failed\n' >&2
    exit 1
fi

rm -rf "$build_dir"
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$repo_dir/cmake/mingw-uurb-toolchain.cmake" \
    '-DCMAKE_C_FLAGS=-D__STDC_NO_THREADS__=1 -Wno-deprecated-declarations' \
    '-DCMAKE_CXX_FLAGS=-D__STDC_NO_THREADS__=1 -Wno-deprecated-declarations' \
    "-DCMAKE_FIND_ROOT_PATH=/usr/x86_64-w64-mingw32;$runtime/mingw64;$runtime/SDL3-3.4.16/x86_64-w64-mingw32;$runtime/SDL3_ttf-3.2.2/x86_64-w64-mingw32" \
    "-DCMAKE_PREFIX_PATH=$runtime/mingw64;$runtime/SDL3-3.4.16/x86_64-w64-mingw32;$runtime/SDL3_ttf-3.2.2/x86_64-w64-mingw32" \
    -DOPENSSL_ROOT_DIR="$runtime/mingw64" \
    -DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER \
    -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY \
    -DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON \
    -DBUILD_SHARED_LIBS=ON \
    -DUSE_UNWIND=OFF \
    -DWITH_VERBOSE_WINPR_ASSERT=OFF \
    -DWITH_INTERNAL_MD4=ON \
    -DWITH_INTERNAL_MD5=ON \
    -DWITH_INTERNAL_RC4=ON \
    -DWITH_NATIVE_SSPI=OFF \
    -DWITH_WINPR_TOOLS=OFF \
    -DWITH_CLIENT_COMMON=ON \
    -DWITH_CLIENT=ON \
    -DWITH_CLIENT_SDL=ON \
    -DWITH_CLIENT_SDL3=ON \
    -DWITH_CLIENT_SDL2=OFF \
    -DWITH_CLIENT_WINDOWS=OFF \
    -DWITH_CLIENT_CHANNELS=ON \
    -DCHANNEL_URBDRC=OFF \
    -DWITH_SERVER=OFF \
    -DWITH_PROXY=OFF \
    -DWITH_SHADOW=OFF \
    -DWITH_SAMPLE=OFF \
    -DWITH_MANPAGES=OFF \
    -DWITH_FFMPEG=OFF \
    -DWITH_SWSCALE=OFF \
    -DWITH_CAIRO=OFF \
    -DWITH_JPEG=OFF \
    -DWITH_KRB5=OFF \
    -DWITH_PKCS11=OFF \
    -DWITH_SMARTCARD_EMULATE=OFF \
    -DWITH_SMARTCARD_INSPECT=OFF \
    -DWITH_FUSE=OFF \
    -DWITH_OPUS=OFF \
    -DWITH_SOXR=OFF \
    -DWITH_YUV=OFF \
    -DWITH_SDL_IMAGE_DIALOGS=OFF \
    -DWITH_SIMD=OFF \
    -DWITH_AVX2=OFF
CCACHE_DISABLE=1 ninja -C "$build_dir" -j "$(nproc)" sdl3-freerdp

output_stage="$(mktemp -d "$(dirname -- "$output_dir")/.freerdp-output.XXXXXXXX")"
cleanup_output_stage() {
    rm -rf -- "$output_stage"
}
trap cleanup_output_stage EXIT

install -m 0755 "$build_dir/client/SDL/SDL3/sdl-freerdp.exe" \
    "$output_stage/sdl-freerdp.exe"
install -m 0755 "$build_dir/winpr/libwinpr/libwinpr3.dll" \
    "$output_stage/libwinpr3.dll"
install -m 0755 "$build_dir/libfreerdp/libfreerdp3.dll" \
    "$output_stage/libfreerdp3.dll"
install -m 0755 "$build_dir/client/common/libfreerdp-client3.dll" \
    "$output_stage/libfreerdp-client3.dll"
install -m 0755 \
    "$runtime/SDL3-3.4.16/x86_64-w64-mingw32/bin/SDL3.dll" \
    "$output_stage/SDL3.dll"
install -m 0755 \
    "$runtime/SDL3_ttf-3.2.2/x86_64-w64-mingw32/bin/SDL3_ttf.dll" \
    "$output_stage/SDL3_ttf.dll"
install -m 0755 \
    "$(x86_64-w64-mingw32-g++-win32 -print-file-name=libgcc_s_seh-1.dll)" \
    "$output_stage/libgcc_s_seh-1.dll"
install -m 0755 \
    "$(x86_64-w64-mingw32-g++-win32 -print-file-name=libstdc++-6.dll)" \
    "$output_stage/libstdc++-6.dll"
install -m 0755 "$runtime/mingw64/bin/libcrypto-3-x64.dll" \
    "$output_stage/libcrypto-3-x64.dll"
install -m 0755 "$runtime/mingw64/bin/libssl-3-x64.dll" \
    "$output_stage/libssl-3-x64.dll"
install -m 0755 "$runtime/mingw64/bin/libcjson-1.dll" \
    "$output_stage/libcjson-1.dll"
install -m 0755 "$runtime/mingw64/bin/liburiparser-1.dll" \
    "$output_stage/liburiparser-1.dll"
mkdir -p "$output_stage/ossl-modules"
install -m 0755 "$runtime/mingw64/lib/ossl-modules/legacy.dll" \
    "$output_stage/ossl-modules/legacy.dll"

printf '%s\n' "$recipe_id" >"$output_stage/.build-recipe"
(
    cd "$output_stage"
    sha256sum \
        sdl-freerdp.exe \
        SDL3.dll \
        SDL3_ttf.dll \
        libfreerdp-client3.dll \
        libfreerdp3.dll \
        libwinpr3.dll \
        libgcc_s_seh-1.dll \
        libstdc++-6.dll \
        libcrypto-3-x64.dll \
        libssl-3-x64.dll \
        libcjson-1.dll \
        liburiparser-1.dll \
        ossl-modules/legacy.dll \
        >.build-sha256
    sha256sum -c .build-sha256 >/dev/null
)

output_previous="${output_dir}.previous.$$"
if [[ -e "$output_dir" ]]; then
    mv -- "$output_dir" "$output_previous"
fi
if mv -- "$output_stage" "$output_dir"; then
    rm -rf -- "$output_previous"
else
    [[ ! -e "$output_previous" ]] || mv -- "$output_previous" "$output_dir"
    exit 1
fi
trap - EXIT

printf 'FreeRDP Windows relay runtime built in %s\n' "$output_dir"
