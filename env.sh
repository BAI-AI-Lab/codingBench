# shellcheck shell=bash
# source this as the bench user: shared settings for every code benchmark
CB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CB
export UV_INDEX_URL=https://mirrors.bfsu.edu.cn/pypi/web/simple
export PIP_INDEX_URL=https://mirrors.bfsu.edu.cn/pypi/web/simple
export UV_PYTHON_INSTALL_DIR=$CB/python
export UV_CACHE_DIR=$CB/.cache/uv
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=$CB/.cache/huggingface
