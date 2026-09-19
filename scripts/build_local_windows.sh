#!/usr/bin/env bash
# This workspace's local cross-toolchain. For native Windows use build_windows.ps1.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
export PATH="$PWD/.tools/llvm-bin:$PWD/.tools/bin:$PWD/.tools/proot/usr/bin:$PATH"
export CARGO_TARGET_DIR="$PWD/.tools/target-windows"
export XWIN_CACHE_DIR="$PWD/.tools/xwin"
export XDG_CACHE_HOME="$PWD/.tools/cache"
export PKG_CONFIG_SYSROOT_DIR="$PWD/.tools/ubuntu"
export PKG_CONFIG_PATH="$PKG_CONFIG_SYSROOT_DIR/usr/lib/x86_64-linux-gnu/pkgconfig:$PKG_CONFIG_SYSROOT_DIR/usr/share/pkgconfig"
npm run build
cargo xwin build --release --locked --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-msvc --features custom-protocol
npx tauri bundle --target x86_64-pc-windows-msvc --bundles nsis --ci
mkdir -p artifacts
cp "$CARGO_TARGET_DIR/x86_64-pc-windows-msvc/release/pipedl.exe" artifacts/PipeDL.exe
cp "$CARGO_TARGET_DIR"/x86_64-pc-windows-msvc/release/bundle/nsis/*-setup.exe artifacts/
(cd artifacts && sha256sum ./*.exe > SHA256SUMS)
