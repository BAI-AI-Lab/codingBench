#!/bin/bash
# PDF of the ladder technical report: figures and tables from the run report, then xelatex + bibtex (Mac or Linux with TeX Live).
set -e
cd "$(dirname "$0")"
PY=${PY:-python3}
$PY analysis.py >/dev/null && $PY make_figures.py . && $PY make_tables.py .
xelatex -interaction=nonstopmode main.tex >/dev/null || true
bibtex main >/dev/null
xelatex -interaction=nonstopmode main.tex >/dev/null || true
xelatex -interaction=nonstopmode main.tex >/dev/null
grep -E "^!|Missing character|undefined" main.log | sort -u | head -20 || true
echo "$(pwd)/main.pdf"
