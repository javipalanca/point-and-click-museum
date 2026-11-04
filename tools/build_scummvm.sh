#!/usr/bin/env bash
# Build ScummVM for the web (WebAssembly) and copy it to vendor/scummvm/.
#
#   tools/build_scummvm.sh                 # ScummVM 2.9.1 with the museum's engines
#   SCUMMVM_VERSION=v2.9.1 ENGINES=scumm,sky tools/build_scummvm.sh
#
# Uses ScummVM's official Emscripten script (dists/emscripten/build.sh), which downloads the
# Emscripten SDK and a few libraries. Needs git, python3, make, a C compiler toolchain and ~5 GB of disk.
# The first build takes 30-60 minutes. ScummVM is GPLv3: see vendor/scummvm/NOTICE.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${SCUMMVM_VERSION:-v2.9.1}"
ENGINES="${ENGINES:-scumm,scumm_7_8,agi,sci,sky,queen,lure,drascula,dreamweb,teenagent,cge,cge2,parallaction,adl,ags}"
WORK="${SCUMMVM_WORK:-$ROOT/.cache/scummvm-$VERSION}"
OUT="$ROOT/vendor/scummvm"

if [[ ! -d "$WORK/.git" ]]; then
  mkdir -p "$(dirname "$WORK")"
  git clone --depth 1 --branch "$VERSION" https://github.com/scummvm/scummvm.git "$WORK"
fi
cd "$WORK"
# Native MIDI drivers make no sense in a browser. ScummVM 2.9.1's configure turns the /dev/sequencer one on for any
# "posix" host, Emscripten included, and backends/midi/seq.cpp then fails: 'sys/soundcard.h' file not found.
# SCUMMVM_CONFIGURE adds options of your own (e.g. --enable-debug).
./dists/emscripten/build.sh setup libs configure make dist \
  --disable-all-engines --enable-plugins --default-dynamic \
  --enable-engine="$ENGINES" --enable-mad --enable-vorbis \
  --disable-seq-midi --disable-timidity --disable-alsa --disable-sndio \
  --prefix=/ --datadir=/data ${SCUMMVM_CONFIGURE:-}

B="$WORK/build-emscripten"
rm -rf "$OUT/scummvm.js" "$OUT/scummvm.wasm" "$OUT/data"
mkdir -p "$OUT"
cp "$B/scummvm.js" "$B/scummvm.wasm" "$OUT/"
cp -R "$B/data" "$OUT/data"
rm -rf "$OUT/data/games"
echo "$VERSION" > "$OUT/VERSION"
echo "$ENGINES" > "$OUT/ENGINES"
du -sh "$OUT"
echo "ScummVM $VERSION -> $OUT  (now run: python3 build.py)"
