# shellcheck shell=bash
# source this as the bench user: shared settings for every code benchmark
CB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CB
# Package and model mirrors in China (the lab server's link); a file $CB/mirrors containing "global" (written by
# deploy/wsl_setup.sh) uses the default PyPI / Hugging Face instead.
if [ "$(cat "$CB/mirrors" 2>/dev/null)" != global ]; then
  export UV_INDEX_URL=https://mirrors.bfsu.edu.cn/pypi/web/simple
  export PIP_INDEX_URL=https://mirrors.bfsu.edu.cn/pypi/web/simple
  export HF_ENDPOINT=https://hf-mirror.com
else
  export HF_ENDPOINT=https://huggingface.co
fi
export UV_PYTHON_INSTALL_DIR=$CB/python
export UV_CACHE_DIR=$CB/.cache/uv
export HF_HOME=$CB/.cache/huggingface
