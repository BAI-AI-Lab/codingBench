"""Run LiveCodeBench for any OpenAI-compatible model without editing lm_styles.py: register $MODEL, then hand
the remaining arguments to the official runner (lcb_runner.runner.main).

The dataset is read from $CB/data/code_generation_lite (the official jsonl files, sha256-checked against the
HF repo) because HF's own download is too slow from here; this only redirects the name passed to load_dataset.
"""
import os
import sys
from datetime import datetime

import datasets

LOCAL = os.path.join(os.environ["CB"], "data", "code_generation_lite")
_load = datasets.load_dataset


def _load_local(path, *args, **kwargs):
    if path == "livecodebench/code_generation_lite" and os.path.isdir(LOCAL):
        path = LOCAL
    return _load(path, *args, **kwargs)


datasets.load_dataset = _load_local  # before lcb_runner imports it

from lcb_runner import lm_styles
from lcb_runner.lm_styles import LanguageModel, LMStyle

name = os.environ["MODEL"]
if name not in lm_styles.LanguageModelStore:
    lm = LanguageModel(name, name.replace("/", "_"), LMStyle.OpenAIChat, datetime(2025, 1, 1))
    lm_styles.LanguageModelList.append(lm)
    lm_styles.LanguageModelStore[name] = lm

# LCB_IDS=<file with one question_id per line>: run exactly those problems (e.g. a fixed sample)
IDS = os.environ.get("LCB_IDS")
if IDS:
    import lcb_runner.benchmarks as _bm

    _want = [l.strip() for l in open(IDS) if l.strip()]
    _orig = _bm.load_code_generation_dataset

    def _load_subset(*args, **kwargs):
        probs = _orig(*args, **kwargs)
        by_id = {p.question_id: p for p in probs}
        missing = [q for q in _want if q not in by_id]
        if missing:
            raise SystemExit(f"LCB_IDS: {len(missing)} ids not in this release/date range, e.g. {missing[:3]}")
        return [by_id[q] for q in _want]

    _bm.load_code_generation_dataset = _load_subset  # before scenario_router imports it

# MAX_TOKENS=none: send no max_tokens at all, so the server lets the model answer up to its full context
if os.environ.get("MAX_TOKENS", "").lower() == "none":
    from lcb_runner.runner import oai_runner as _oai

    _init = _oai.OpenAIRunner.__init__

    def _init_no_limit(self, *args, **kwargs):
        _init(self, *args, **kwargs)
        self.client_kwargs.pop("max_tokens", None)
        self.client_kwargs.pop("max_completion_tokens", None)

    _oai.OpenAIRunner.__init__ = _init_no_limit

from lcb_runner.runner import main as lcb_main  # noqa: E402  (after registering)

if __name__ == "__main__":  # the runner's worker processes are spawned and re-import this file
    sys.argv = ["lcb_runner.runner.main", "--model", name] + sys.argv[1:]
    lcb_main.main()
