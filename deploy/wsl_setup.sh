#!/bin/bash
# One-time setup of the ladder test set on a workstation: Windows with WSL2 (Ubuntu), or any x86 Linux box.
# Run from a checkout of this repo, inside WSL:
#
#   sudo bash deploy/wsl_setup.sh                                   # download the data (about 6 min on a fast link)
#   sudo bash deploy/wsl_setup.sh --data /mnt/e/codingBench_ladder/raw   # copy it from a drive instead, then verify
#   CB=/other/dir sudo -E bash deploy/wsl_setup.sh
#   LADDER_LIST=part.tsv.gz sudo -E bash deploy/wsl_setup.sh             # only part of the download list (CI uses this)
#
# Same layout as the lab server: the install dir and its scripts are root-owned, model-generated code runs as the
# unprivileged user "bench". Only the ladder's two Python envs are installed (install.sh --ladder), packages come
# from the default PyPI ($CB/mirrors = global), and the problems are built, calibrated against the official
# solutions, and listed in $CB/data/ladder/ladder.json. Afterwards:  export MODEL=... OPENAI_BASE_URL=...
# OPENAI_API_KEY=...;  cb ladder --smoke;  cb ladder
set -euo pipefail
SRC=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
export CB=${CB:-/opt/code_bench}
DATA=
[ "${1:-}" = --data ] && DATA=${2:?usage: wsl_setup.sh [--data <raw dir>]}
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
t() { echo "[$(date +%T)] $*"; }

t "packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq g++ make python3 curl git rsync ca-certificates sudo >/dev/null

t "install dir $CB (user bench)"
mkdir -p "$CB"
bash "$SRC/deploy/setup.sh"
echo global > "$CB/mirrors"
mkdir -p "$CB/data/ladder/raw"
chown -R bench:bench "$CB/data"

t "python envs (as bench)"
sudo -u bench -H bash "$CB/install.sh" --ladder

if [ -n "$DATA" ]; then
  t "copying the data from $DATA"
  rsync -rt --exclude='._*' --exclude='*.part' "$DATA/" "$CB/data/ladder/raw/"
  chown -R bench:bench "$CB/data/ladder/raw"
fi
t "data: download what is missing and check every file (git sha1, zip CRC)"
cb ladder-fetch --workers 16

t "build the problems, judge the official solutions, write the problem list"
cb ladder-build
cb ladder-build --calibrate --workers "$(nproc)"
cb ladder-build --manifest "$CB/data/ladder/ladder.json"
t "READY: export MODEL=... OPENAI_BASE_URL=... OPENAI_API_KEY=...; cb ladder --smoke; cb ladder"
