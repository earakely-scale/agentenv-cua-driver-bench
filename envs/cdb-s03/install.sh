#!/bin/sh
# Run as root once the app's downloads are in: unpack the runtimes they brought for this arch, Electron, and Node where
# the task needs it, in place of their archives.
set -e
for zip in runtime/electron-*.zip; do
    [ -e "$zip" ] || continue
    unzip -q "$zip" -d runtime/electron
    rm "$zip"
done
for tarball in runtime/node-*.tar.xz; do
    [ -e "$tarball" ] || continue
    mkdir -p runtime/node
    tar -xJf "$tarball" -C runtime/node --strip-components=1
    rm "$tarball"
done
test -x runtime/electron/electron
