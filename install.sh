#!/bin/bash
# Install the benchmark code, Python envs and data. Run as user bench:  sudo -u bench -H bash <install dir>/install.sh
# (--ladder: only the ladder test set's two envs, e.g. on a workstation; see deploy/wsl_setup.sh)
# One venv per benchmark under $CB/venvs; safe to re-run.
set -e
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/env.sh"
cd $CB
t() { echo "[$(date +%T)] $*"; }
if [ "${1:-}" = --ladder ]; then  # only the ladder test set: generation/judge env and the static-quality env
  export PATH=$CB/.local/bin:$PATH   # before the check, so a re-run finds the uv it installed
  # HOME/XDG_CONFIG_HOME explicitly: sudo may keep the calling user's, and the installer writes a receipt there
  command -v uv >/dev/null || { t "uv"; curl -LsSf https://astral.sh/uv/install.sh | env HOME=$CB XDG_CONFIG_HOME=$CB/.cache/config \
    UV_INSTALL_DIR=$CB/.local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null; }
  mkdir -p venvs data/ladder runs
  t "python"; uv python install 3.12 2>&1 | tail -1
  t "ladder venv (generation, judge, report)"
  uv venv -q --allow-existing -p 3.12 venvs/ladder
  VIRTUAL_ENV=$CB/venvs/ladder uv pip install -q "openai>=1.40" httpx pyyaml
  t "quality venv (static code quality, the pinned versions of arXiv:2610.19167)"
  uv venv -q --allow-existing -p 3.12 venvs/quality
  VIRTUAL_ENV=$CB/venvs/quality uv pip install -q pylint==3.3.5 radon==6.0.1
  t "LADDER INSTALL DONE"
  exit 0
fi
t "repos (pinned to the commits this was tested with)"
mkdir -p src venvs data runs
for r in bigcode-project/bigcodebench@09dd993 LiveCodeBench/LiveCodeBench@28fef95 facebookresearch/cruxeval@190faf1; do
  repo=${r%@*}; commit=${r#*@}; d=src/$(basename $repo)
  [ -d $d ] || git clone -q https://github.com/$repo $d
  git -C $d fetch -q --depth 1 origin $commit 2>/dev/null || true
  git -C $d checkout -q $commit && echo "$d $(git -C $d log -1 --format='%h %cs')"
done
t "python"; uv python install 3.10 3.11 3.12 2>&1 | tail -2
t "bigcodebench venv"
uv venv -q --allow-existing -p 3.10 venvs/bigcodebench
VIRTUAL_ENV=$CB/venvs/bigcodebench uv pip install -q -e src/bigcodebench --no-deps
VIRTUAL_ENV=$CB/venvs/bigcodebench uv pip install -q appdirs fire multipledispatch pqdm tempdir termcolor tqdm "tree_sitter>=0.22" "tree-sitter-python>=0.21" wget datasets transformers numpy rich openai gradio-client e2b anthropic google-genai "mistralai<1"
t "bigcodebench eval requirements ($(wc -l < src/bigcodebench/Requirements/requirements-eval.txt) lines)"
VIRTUAL_ENV=$CB/venvs/bigcodebench uv pip install -q -r src/bigcodebench/Requirements/requirements-eval.txt 2>&1 | tail -5
t "livecodebench venv"
uv venv -q --allow-existing -p 3.11 venvs/livecodebench
VIRTUAL_ENV=$CB/venvs/livecodebench uv pip install -q -e src/LiveCodeBench --no-deps
VIRTUAL_ENV=$CB/venvs/livecodebench uv pip install -q annotated-types anthropic==0.42.0 cohere "datasets<4" google-genai mistralai==0.4.2 openai pebble torch together
t "cruxeval venv"
uv venv -q --allow-existing -p 3.10 venvs/cruxeval
VIRTUAL_ENV=$CB/venvs/cruxeval uv pip install -q openai numpy tabulate
t "quality venv (static code quality, the pinned versions of arXiv:2610.19167)"
uv venv -q --allow-existing -p 3.12 venvs/quality
VIRTUAL_ENV=$CB/venvs/quality uv pip install -q pylint==3.3.5 radon==6.0.1
t "data: bigcodebench-hard"
venvs/bigcodebench/bin/python -c "
from datasets import load_dataset
d = load_dataset('bigcode/bigcodebench-hard', split='v0.1.4'); print('bcb-hard', len(d))"
t "data: livecodebench code_generation_lite (OpenCompass Aliyun mirror, sha256-checked against the HF repo)"
D=$CB/data/code_generation_lite; mkdir -p $D
if [ ! -f $D/test6.jsonl ]; then
  curl -s -C - -o $CB/data/lcb.zip http://opencompass.oss-cn-shanghai.aliyuncs.com/datasets/data/code_generation_lite.zip
  venvs/livecodebench/bin/python -c "import zipfile; zipfile.ZipFile('$CB/data/lcb.zip').extractall('$CB/data/lcb_zip')"
  mv $CB/data/lcb_zip/code_generation_lite/*.jsonl $CB/data/lcb_zip/code_generation_lite/code_generation_lite.py $D/
  rm -rf $CB/data/lcb.zip $CB/data/lcb_zip
fi
for f in test.jsonl test2.jsonl test3.jsonl test4.jsonl test5.jsonl test6.jsonl; do
  want=$(curl -sL -m 60 "$HF_ENDPOINT/datasets/livecodebench/code_generation_lite/raw/main/$f" | sed -n "s/^oid sha256://p")
  [ -n "$want" ] && [ "$want" = "$(sha256sum $D/$f | cut -d' ' -f1)" ] && echo "ok  $f" || { echo "BAD $f"; exit 1; }
done
t "sizes"; du -sh venvs/* python data 2>/dev/null
t "INSTALL DONE"
