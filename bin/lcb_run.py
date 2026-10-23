"""Run LiveCodeBench for any OpenAI-compatible model without editing lm_styles.py: register $MODEL, then hand
the remaining arguments to the official runner (lcb_runner.runner.main).

The dataset is read from $CB/data/code_generation_lite (the official jsonl files, sha256-checked against the
HF repo) because HF's own download is too slow from here; this only redirects the name passed to load_dataset.
"""
import json
import os
import sys
import time
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

# LCB_OMIT=temperature,top_p,...: drop these request fields, for models that fix them and reject them (Kimi K3.1 Pro)
OMIT = [k.strip() for k in os.environ.get("LCB_OMIT", "").split(",") if k.strip()]
if OMIT:
    from lcb_runner.runner import oai_runner as _oai

    _init_omit = _oai.OpenAIRunner.__init__

    def _init_without(self, *args, **kwargs):
        _init_omit(self, *args, **kwargs)
        for k in OMIT:
            self.client_kwargs.pop(k, None)

    _oai.OpenAIRunner.__init__ = _init_without

# LCB keeps every answer in memory and writes them only when all problems are done, and a problem whose retries
# run out returns no answer, which fails an assert and loses the whole run. Give such a problem an empty answer
# (graded as a failure) instead, and once the account is out of balance stop calling the API in that worker.
from lcb_runner.runner import oai_runner as _oai  # noqa: E402

_run_single = _oai.OpenAIRunner._run_single
_broke = []


def _run_single_safe(self, prompt, n=10):
    if _broke:
        return [""] * self.args.n
    return _run_single(self, prompt, n) or [""] * self.args.n


def _is_out_of_balance(e):
    text = repr(e).lower()
    return getattr(e, "status_code", None) == 402 or any(
        s in text for s in ("insufficient balance", "insufficient_balance", "exceeded_current_quota", "suspended"))


_run_single_safe.__name__ = "_run_single"  # workers get the bound method pickled by name
_oai.OpenAIRunner._run_single = _run_single_safe

# LCB_USAGE_LOG=<file>: append one JSON line per API call (start/end time, usage, finish reason, or the error),
# so tools/lcb_usage.py can report latency and tokens. Retries after an error are logged as separate calls.
USAGE = os.environ.get("LCB_USAGE_LOG")
_completions = _oai.OpenAIRunner.client.chat.completions
_create = _completions.create


def _log(rec):
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode()
    fd = os.open(USAGE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)  # one O_APPEND write per call, so parallel workers don't interleave lines
    finally:
        os.close(fd)


def _create_checked(*args, **kwargs):
    rec = {"start": time.time(), "messages": kwargs.get("messages")}
    try:
        r = _create(*args, **kwargs)
    except Exception as e:
        if _is_out_of_balance(e):
            _broke.append(1)
        if USAGE:
            rec.update(end=time.time(), error=repr(e)[:500])
            _log(rec)
        raise
    if USAGE:
        rec.update(end=time.time(), model=r.model, usage=r.usage.model_dump() if r.usage else None,
                   finish=[c.finish_reason for c in r.choices],
                   chars=[len(c.message.content or "") for c in r.choices])
        _log(rec)
    return r


_completions.create = _create_checked

from lcb_runner.runner import main as lcb_main  # noqa: E402  (after registering)

if __name__ == "__main__":  # the runner's worker processes are spawned and re-import this file
    sys.argv = ["lcb_runner.runner.main", "--model", name] + sys.argv[1:]
    lcb_main.main()
