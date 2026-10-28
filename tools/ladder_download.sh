#!/bin/bash
# Resumable bulk download for the ladder test set: ladder_download.sh <list.tsv> <dest dir> [parallel]
# list.tsv: url<TAB>relative path<TAB>size in bytes (-1 = unknown)[<TAB>git blob sha1, checked by ladder_fetch.py --verify]. Files already complete are skipped, partial
# ones resume (curl -C -), stalls (<100 B/s for 2 min) are retried with back-off, so it can be killed and re-run
# at any time. Meant for the server's slow inbound link: run it under nohup and check with --status.
# LADDER_RATE=25k caps every connection (curl --limit-rate), e.g. to leave room for API streams during a run.
set -u
list=$1; dest=$2; par=${3:-6}
if [ "$list" = --status ]; then
  list=$2; dest=$3
  awk -F'\t' -v d="$dest" 'BEGIN{n=0;ok=0;b=0;t=0} {n++; f=d"/"$2; if ($3>0) t+=$3; cmd="stat -c %s \"" f "\" 2>/dev/null"; s=""; cmd | getline s; close(cmd); if (s!="" && ($3<0 || s==$3)) {ok++; if ($3>0) b+=$3}} END{printf "%d/%d files, %.0f/%.0f MB\n", ok, n, b/1e6, t/1e6}' "$list"
  exit
fi
one() {
  local url=$1 rel=$2 size=$3 f=$dest/$2 i lim=()
  [ -n "${LADDER_RATE:-}" ] && lim=(--limit-rate "$LADDER_RATE")
  if [ -f "$f" ] && { [ "$size" -lt 0 ] || [ "$(stat -c %s "$f")" = "$size" ]; }; then return 0; fi
  mkdir -p "$(dirname "$f")"
  for i in $(seq 1 60); do
    if [ "$size" -lt 0 ]; then
      curl -sfL -m 600 "${lim[@]}" -A 'Mozilla/5.0 (codingBench; academic benchmark)' -o "$f.part" "$url" && mv "$f.part" "$f" && return 0
    else
      curl -sfL -C - --speed-limit 100 --speed-time 120 "${lim[@]}" -A 'Mozilla/5.0 (codingBench; academic benchmark)' -o "$f.part" "$url"
      [ -f "$f.part" ] && [ "$(stat -c %s "$f.part")" = "$size" ] && mv "$f.part" "$f" && return 0
      [ -f "$f.part" ] && [ "$(stat -c %s "$f.part")" -gt "$size" ] && rm -f "$f.part"   # wrong file: start over
    fi
    sleep $(( i < 10 ? i * 5 : 60 ))
  done
  echo "FAILED $url" >&2; return 1
}
export -f one; export dest LADDER_RATE
xargs -P "$par" -d '\n' -n 1 bash -c 'IFS=$'"'\t'"' read -r u r s _ <<< "$1"; one "$u" "$r" "$s"' _ < "$list"
echo "done $(date +%F\ %T)"
