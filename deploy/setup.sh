#!/bin/bash
# Install or update codingBench on a server, from a checkout of this repo. Run as root.
#
#   deploy/setup.sh            # create user bench and the install dir, copy the scripts, link /usr/local/bin/cb
#   deploy/setup.sh --check    # only show what would change
#   CB=/other/dir deploy/setup.sh
#
# Then, once (and after changing install.sh):  sudo -u bench -H bash $CB/install.sh
#
# Layout: the install dir and the scripts in it are root-owned, so code that a model writes (it runs as bench)
# can't replace a script that root launches. bench can only write its work dirs (runs, venvs, data, ...).
set -euo pipefail
SRC=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
CB=${CB:-/data/hx/code_bench}
CHECK=0; [ "${1:-}" = --check ] && CHECK=1
FILES="bin/cb:755 bin/lcb_run.py:644 bin/crux_run.py:644 tools/lcb_report.py:644 tools/lcb_usage.py:644 tools/lcb_rejudge.py:644 tools/lcb_quality.py:644 tools/lcb_progress.py:644 tools/lcb_perf.py:644 env.sh:644 install.sh:644
       README.md:644 SURVEY.md:644 samples/lcb_newest100.txt:644 samples/lcb_newest35.txt:644
       bin/ladder_run.py:644 tools/ladder_lib.py:644 tools/ladder_build.py:644 tools/ladder_judge.py:644
       tools/ladder_quality.py:644 tools/ladder_report.py:644 tools/ladder_figures.py:644 tools/ladder_complexity.py:644 tools/ladder_download.sh:644 tools/ladder_sources.py:644 tools/ladder_fetch.py:644
       samples/ladder_download.tsv.gz:644 samples/models.json:644 tests/mock_openai.py:644"
WORK="src venvs data runs python .cache .local"

changed=0
for fp in $FILES; do
  f=${fp%:*}; mode=${fp#*:}
  if ! cmp -s "$SRC/$f" "$CB/$f"; then
    echo "changed  $CB/$f"; changed=1
    [ $CHECK = 1 ] || install -D -o root -g root -m "$mode" "$SRC/$f" "$CB/$f"
  fi
done
[ $changed = 1 ] || echo "files: all up to date"
[ $CHECK = 1 ] && exit 0

id bench >/dev/null 2>&1 || useradd --system --home-dir "$CB" --no-create-home --shell /bin/bash bench
chown root:root "$CB" "$CB/bin" "$CB/tools" "$CB/samples" "$CB/tests"; chmod 755 "$CB" "$CB/bin" "$CB/tools" "$CB/samples" "$CB/tests"
for d in $WORK; do mkdir -p "$CB/$d"; chown bench:bench "$CB/$d"; done
ln -sfn "$CB/bin/cb" /usr/local/bin/cb
echo "installed to $CB; if install.sh changed or this is a new server: sudo -u bench -H bash $CB/install.sh"
