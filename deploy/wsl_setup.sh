#!/bin/bash
# One-time setup of the ladder test set on a workstation: Windows with WSL2 (Ubuntu), or any x86 Linux box.
# Run from a checkout of this repo, inside WSL:
#
#   sudo bash deploy/wsl_setup.sh                                   # download the data (about 6 min on a fast link)
#   sudo bash deploy/wsl_setup.sh --data /mnt/e/codingBench_ladder/raw   # copy it from a drive instead, then verify
#   CB=/other/dir sudo -E bash deploy/wsl_setup.sh
#   LADDER_LIST=part.tsv.gz sudo -E bash deploy/wsl_setup.sh             # only part of the download list (CI uses this)
#   sudo bash deploy/wsl_setup.sh --skip-calibrate   # build and list the problems, judge the official solutions later
#                                                    # (cb ladder-build --calibrate; worth it on a machine with few cores)
# In China (e.g. an AutoDL / SeetaCloud box): CB_MIRRORS=cn keeps PyPI on the BFSU mirror; GitHub via the provider's
# proxy works if http(s)_proxy is exported (with no_proxy covering the mirrors and the model API); they reach bench.
#
# Same layout as the lab server: the install dir and its scripts are root-owned, model-generated code runs as the
# unprivileged user "bench". Only the ladder's two Python envs are installed (install.sh --ladder), packages come
# from the default PyPI ($CB/mirrors = global), and the problems are built, calibrated against the official
# solutions, and listed in $CB/data/ladder/ladder.json. Afterwards:  export MODEL=... OPENAI_BASE_URL=...
# OPENAI_API_KEY=...;  cb ladder --smoke;  cb ladder
set -euo pipefail
SRC=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
export CB=${CB:-/opt/code_bench}
DATA= CALIBRATE=1
while [ $# -gt 0 ]; do
  case $1 in
    --data) DATA=${2:?usage: wsl_setup.sh [--data <raw dir>] [--skip-calibrate]}; shift 2 ;;
    --skip-calibrate) CALIBRATE=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done
PROXY=http_proxy,https_proxy,no_proxy,HTTP_PROXY,HTTPS_PROXY,NO_PROXY,REQUESTS_CA_BUNDLE,SSL_CERT_FILE
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
t() { echo "[$(date +%T)] $*"; }

t "packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq g++ make python3 curl git rsync ca-certificates sudo >/dev/null

t "install dir $CB (user bench)"
mkdir -p "$CB"
bash "$SRC/deploy/setup.sh"
[ "${CB_MIRRORS:-global}" = cn ] && rm -f "$CB/mirrors" || echo global > "$CB/mirrors"
mkdir -p "$CB/data/ladder/raw"
chown -R bench:bench "$CB/data"

t "python envs (as bench)"
sudo -u bench -H --preserve-env=$PROXY bash "$CB/install.sh" --ladder

if [ -n "$DATA" ]; then
  t "copying the data from $DATA"
  rsync -rt --exclude='._*' --exclude='*.part' "$DATA/" "$CB/data/ladder/raw/"
  chown -R bench:bench "$CB/data/ladder/raw"
fi
t "data: download what is missing and check every file (git sha1, zip CRC)"
cb ladder-fetch --workers 16

t "build the problems, judge the official solutions, write the problem list"
cb ladder-build
[ $CALIBRATE = 1 ] && cb ladder-build --calibrate --workers "$(nproc)"
cb ladder-build --manifest "$CB/data/ladder/ladder.json"
t "READY: export MODEL=... OPENAI_BASE_URL=... OPENAI_API_KEY=...; cb ladder --smoke; cb ladder"
