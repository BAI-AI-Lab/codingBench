#!/bin/bash
# PDF of this report (xelatex with ctex; Times New Roman + Kaiti on the Mac)
cd "$(dirname "$0")" && xelatex -interaction=nonstopmode main.tex >/dev/null && xelatex -interaction=nonstopmode main.tex >/dev/null && echo "$(pwd)/main.pdf"
