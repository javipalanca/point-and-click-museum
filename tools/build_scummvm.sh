#!/usr/bin/env bash
# Build ScummVM for the web (WebAssembly) and copy it to vendor/scummvm/.
#
#   tools/build_scummvm.sh                 # ScummVM 2.9.1 with the museum's engines
#   ENGINES=all tools/build_scummvm.sh     # every stable engine, with the libraries they need
#   ENGINES=all-unstable tools/build_scummvm.sh   # also the engines ScummVM marks as unstable (may not work)
#   SCUMMVM_VERSION=v2.9.1 ENGINES=scumm,sky tools/build_scummvm.sh
#
# Uses ScummVM's official Emscripten script (dists/emscripten/build.sh), which downloads the
# Emscripten SDK and a few libraries. Needs git, python3, make, a C compiler toolchain and ~5 GB of disk.
# The first build takes 30-60 minutes (with ENGINES=all, a few hours and ~15 GB). ScummVM is GPLv3: see
# vendor/scummvm/NOTICE.md. Engines are dynamic plugins: the player only loads the one each game needs.
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

# ScummVM's Emscripten script downloads with `wget -nc`. A ~/.wgetrc (or system wgetrc) with timestamping=on makes
# wget refuse that ("can't timestamp and not clobber old files at the same time"), so during the build wget runs
# with --no-config, through a small wrapper first in PATH. Your own wget settings are not touched.
if ! command -v wget >/dev/null 2>&1; then
  echo "error: ScummVM's build script needs wget (macOS: brew install wget; Debian/Ubuntu: apt install wget)" >&2
  exit 1
fi
REAL_WGET="$(command -v wget)"
SHIM="$ROOT/.cache/wget-shim"
mkdir -p "$SHIM"
printf '#!/bin/sh\nexec "%s" --no-config "$@"\n' "$REAL_WGET" > "$SHIM/wget"
chmod +x "$SHIM/wget"
export PATH="$SHIM:$PATH"
case "$ENGINES" in
  all)          ENGINE_FLAGS=() ;;                         # configure's default: every stable engine
  all-unstable) ENGINE_FLAGS=(--enable-all-engines) ;;
  *)            ENGINE_FLAGS=(--disable-all-engines "--enable-engine=$ENGINES") ;;
esac
# libraries some engines need (videos, PNG/JPEG images, fonts…); the Emscripten script fetches or builds them.
# With a short engine list they are not needed; configure leaves out any engine whose libraries are missing.
LIB_FLAGS=(--enable-mad --enable-vorbis)
if [[ "$ENGINES" == all* ]]; then
  LIB_FLAGS+=(--enable-ogg --enable-zlib --enable-png --enable-jpeg --enable-gif --enable-freetype2 \
              --enable-theoradec --enable-mpeg2 --enable-a52 --enable-faad)
fi
# Native MIDI drivers make no sense in a browser. ScummVM 2.9.1's configure turns the /dev/sequencer one on for any
# "posix" host, Emscripten included, and backends/midi/seq.cpp then fails: 'sys/soundcard.h' file not found.
# SCUMMVM_CONFIGURE adds options of your own (e.g. --enable-debug).
# ${ARR[@]+"${ARR[@]}"}: an empty list must not trip `set -u` in macOS's bash 3.2
./dists/emscripten/build.sh setup libs configure make dist \
  --enable-plugins --default-dynamic ${ENGINE_FLAGS[@]+"${ENGINE_FLAGS[@]}"} "${LIB_FLAGS[@]}" \
  --disable-seq-midi --disable-timidity --disable-alsa --disable-sndio \
  --prefix=/ --datadir=/data ${SCUMMVM_CONFIGURE:-}

B="$WORK/build-emscripten"
rm -rf "$OUT/scummvm.js" "$OUT/scummvm.wasm" "$OUT/data"
mkdir -p "$OUT"
cp "$B/scummvm.js" "$B/scummvm.wasm" "$OUT/"
cp -R "$B/data" "$OUT/data"
rm -rf "$OUT/data/games"
echo "$VERSION" > "$OUT/VERSION"
# the engines really built (one plugin each), for the catalogue: tools/game_fetch.py reads this list
PLUGINS=$(find "$OUT/data/plugins" -name 'lib*.so' 2>/dev/null | sed 's#.*/lib##; s#\.so$##' | grep -v '^detection$' | sort | paste -sd, -)
echo "${PLUGINS:-$ENGINES}" > "$OUT/ENGINES"
echo "engines: $(tr ',' '\n' < "$OUT/ENGINES" | wc -l | tr -d ' ') ($(cat "$OUT/ENGINES"))"
du -sh "$OUT"
echo "ScummVM $VERSION -> $OUT  (now run: python3 build.py)"
