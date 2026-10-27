#!/usr/bin/env bash
# Only the pinned source archives supplied by build_windows_source_engines.py
# are used. Run in an MSYS2 MINGW64 shell with gcc/make/pkgconf/nasm/meson/ninja.
set -euo pipefail
sources=$(cygpath -u "$1")
prefix=$(cygpath -u "$2")
work=$(cygpath -u "$3")
jobs=${CITRICA_BUILD_JOBS:-2}
export SOURCE_DATE_EPOCH=1789776000
export PATH="/mingw64/bin:/usr/bin"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
mkdir -p "$prefix" "$work"
pacman -Q > "$work/msys2-packages.txt"
gcc --version > "$work/gcc-version.txt"
nasm -v > "$work/nasm-version.txt"
if [ -d /mingw64/share/licenses ]; then
    cp -R /mingw64/share/licenses "$work/toolchain-licenses"
fi

build_autoconf() {
    local name=$1
    shift
    mkdir -p "$work/$name"
    pushd "$work/$name"
    "$sources/$name/configure" --prefix="$prefix" --disable-shared --enable-static "$@"
    make -j"$jobs"
    make install
    popd
}

build_autoconf ogg --disable-docs
build_autoconf vorbis --disable-docs --with-ogg="$prefix"
build_autoconf opus --disable-doc --disable-extra-programs --disable-intrinsics
build_autoconf lame --disable-frontend --disable-decoder

mkdir -p "$work/x264"
pushd "$work/x264"
"$sources/x264/configure" --prefix="$prefix" --enable-static --disable-cli --disable-opencl
make -j"$jobs"
make install
popd

mkdir -p "$work/vpx"
pushd "$work/vpx"
"$sources/vpx/configure" --prefix="$prefix" --target=x86_64-win64-gcc --as=nasm \
    --disable-shared --enable-static --disable-examples --disable-tools --disable-docs --disable-unit-tests
make -j"$jobs"
make install
popd

meson setup "$work/dav1d" "$sources/dav1d" --prefix="$prefix" --libdir=lib \
    --default-library=static -Denable_tools=false -Denable_tests=false -Denable_docs=false
ninja -C "$work/dav1d" -j"$jobs"
ninja -C "$work/dav1d" install

# zlib's generated makefile supports an out-of-tree build.
mkdir -p "$work/zlib"
pushd "$work/zlib"
"$sources/zlib/configure" --static --prefix="$prefix"
make -j"$jobs"
make install
popd

mkdir -p "$work/ffmpeg"
pushd "$work/ffmpeg"
"$sources/ffmpeg/configure" --prefix="$prefix" --target-os=mingw32 --arch=x86_64 \
    --enable-gpl --enable-version3 --disable-autodetect --disable-shared --enable-static \
    --disable-debug --disable-doc --disable-ffplay --disable-network --enable-w32threads \
    --enable-libx264 --enable-libmp3lame --enable-libvorbis --enable-libopus --enable-libvpx \
    --enable-libdav1d --enable-zlib --pkg-config-flags=--static \
    --extra-cflags="-I$prefix/include" --extra-ldflags="-L$prefix/lib -static" \
    --extra-libs="-lstdc++ -lpthread -lm" --extra-version=citrica-source
make -j"$jobs"
make install
popd
"$prefix/bin/ffmpeg.exe" -hide_banner -version > "$work/ffmpeg-version.txt"
"$prefix/bin/ffmpeg.exe" -hide_banner -buildconf > "$work/ffmpeg-buildconf.txt" 2>&1
"$prefix/bin/ffprobe.exe" -hide_banner -version > "$work/ffprobe-version.txt"
