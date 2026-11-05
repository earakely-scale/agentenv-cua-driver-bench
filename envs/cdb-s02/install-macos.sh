#!/bin/bash
# Run as the session user once the app's downloads are in: unpack Electron, and Node and Chrome for Testing where the
# task needs them, in place of their archives, and copy LibreOffice and GnuCash, where it needs them, out of their disk
# images into /Applications, where the task's macOS descriptor runs them.
set -euo pipefail
shopt -s nullglob
for zip in runtime/electron-*.zip; do
    ditto -x -k "$zip" runtime/electron
    rm "$zip"
done
for tarball in runtime/node-*.tar.xz; do
    mkdir -p runtime/node
    tar -xJf "$tarball" -C runtime/node --strip-components=1
    rm "$tarball"
done
for zip in runtime/chromium-*.zip; do
    ditto -x -k "$zip" runtime/chromium-unpacked
    mv runtime/chromium-unpacked/* runtime/chromium
    rmdir runtime/chromium-unpacked
    rm "$zip"
done
for image in runtime/*.dmg; do
    mount=$(mktemp -d)
    hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mount" "$image" > /dev/null
    for app in "$mount"/*.app; do
        rm -rf "/Applications/$(basename "$app")"
        ditto "$app" "/Applications/$(basename "$app")"
    done
    hdiutil detach "$mount" > /dev/null
    rm "$image"
done
test -x runtime/electron/Electron.app/Contents/MacOS/Electron
