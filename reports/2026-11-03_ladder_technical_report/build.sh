#!/bin/bash
# PDF of the codingBench ladder technical report: data, statistics, figures and tables, then xelatex + bibtex.
set -e
cd "$(dirname "$0")"
PY=${PY:-python3}
[ -d data/dirs ] && $PY collect.py .
$PY analysis.py . >/dev/null && $PY make_figures.py . && $PY make_tables.py .
xelatex -interaction=nonstopmode main.tex >/dev/null || true
bibtex main >/dev/null
xelatex -interaction=nonstopmode main.tex >/dev/null || true
xelatex -interaction=nonstopmode main.tex >/dev/null
grep -E "^!|Missing character|undefined" main.log | sort -u | head -20 || true
echo "$(pwd)/main.pdf"
