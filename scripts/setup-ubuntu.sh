#!/usr/bin/env bash
# Idempotent toolchain setup for pixel-snap-voice on Ubuntu 24.04 (noble).
# Works on a dev box, a CI runner, a container, or any cloud coding agent:
#   bash scripts/setup-ubuntu.sh
# Adds the hardware/sim toolchain that the repo's checks and README expect:
#   - build-essential + cmake  -> host recorder simulation (sim/host)
#   - ngspice                  -> power-path SPICE sim (sim/spice/power_path.cir)
#   - KiCad 10 (kicad-cli +    -> schematic/PCB ship gates and pcbnew scripts
#     pcbnew python module,        (verify_schematic.py, check_gates.py, DRC, gerbers)
#     footprints, symbols)
#   - freerouting              -> autorouter driven by route_pcb.py
# Needs python3 and git already present. Safe to run repeatedly. Runs apt
# through sudo unless it is already root (many containers have no sudo).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KICAD_PPA="ppa:kicad/kicad-10.0-releases"
KICAD_LIST="/etc/apt/sources.list.d/kicad-ubuntu-kicad-10_0-releases-noble.sources"
FREEROUTING_VER="2.4.1"
FREEROUTING_DIR="/opt/freerouting"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

echo "== apt: base packages =="
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  software-properties-common ca-certificates build-essential cmake ngspice \
  curl unzip

# KiCad 10 is newer than the Ubuntu 24.04 archive (which ships KiCad 7), so pull
# it from the official KiCad releases PPA. add-apt-repository is a no-op if the
# source already exists.
if [ ! -f "$KICAD_LIST" ]; then
  echo "== apt: adding KiCad 10 PPA =="
  $SUDO add-apt-repository -y "$KICAD_PPA"
fi

echo "== apt: KiCad 10 =="
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  kicad kicad-footprints kicad-symbols

# freerouting is the autorouter route_pcb.py drives over Specctra DSN/SES.
# The published .jar needs a newer JRE than Ubuntu 24.04 ships, so take the
# linux-x64 bundle, which carries its own runtime.
if [ ! -x "$FREEROUTING_DIR/bin/freerouting" ]; then
  echo "== freerouting $FREEROUTING_VER =="
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/fr.zip" \
    "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VER}/freerouting-${FREEROUTING_VER}-linux-x64.zip"
  unzip -q "$tmp/fr.zip" -d "$tmp"
  $SUDO rm -rf "$FREEROUTING_DIR"
  $SUDO mv "$tmp/freerouting-${FREEROUTING_VER}-linux-x64" "$FREEROUTING_DIR"
  $SUDO chmod +x "$FREEROUTING_DIR/bin/freerouting"
  rm -rf "$tmp"
fi

echo "== toolchain versions =="
kicad-cli version
ngspice --version | head -1 || true
python3 -c "import pcbnew; print('pcbnew', pcbnew.Version())" 2>/dev/null
"$FREEROUTING_DIR/bin/freerouting" -h 2>&1 | head -1 || true

echo "== build host recorder simulation =="
cmake -S "$REPO/sim/host" -B "$REPO/build/host"
cmake --build "$REPO/build/host"

echo "== setup-ubuntu.sh done =="
