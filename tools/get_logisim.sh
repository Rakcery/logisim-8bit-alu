#!/usr/bin/env bash
# Download Logisim Evolution 4.0.0 (the version this project targets) to
# tools/.cache/logisim-evolution-4.0.0-all.jar and print its path.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/.cache"
jar="$dir/logisim-evolution-4.0.0-all.jar"
if [ ! -f "$jar" ]; then
  mkdir -p "$dir"
  curl -fsSL -o "$jar" \
    https://github.com/logisim-evolution/logisim-evolution/releases/download/v4.0.0/logisim-evolution-4.0.0-all.jar
fi
echo "$jar"
