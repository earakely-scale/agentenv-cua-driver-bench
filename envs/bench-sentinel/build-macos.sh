#!/bin/bash
# trycua's BenchLab.app and BenchSentinel.app, built into apps/ from their pinned sources by their build.sh.
set -euo pipefail
bash swift/build.sh apps
