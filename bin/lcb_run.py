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

# LCB_USAGE_LOG=<file>: append one JSON line per API call (see _create_checked below)
USAGE = os.environ.get("LCB_USAGE_LOG")
PROBLEMS = os.path.join(os.path.dirname(USAGE), "problems.json") if USAGE else None

# LCB_IDS=<file with one question_id per line>: run exactly those problems (e.g. a fixed sample). The problems of the
# run are also written to problems.json next to the usage log, so every logged call carries its question_id and
# cb progress can name the problems while the run is going.
IDS = os.environ.get("LCB_IDS")
import lcb_runner.benchmarks as _bm  # noqa: E402

_orig = _bm.load_code_generation_dataset


def _load_problems(*args, **kwargs):
    probs = _orig(*args, **kwargs)
    if IDS:
        want = [l.strip() for l in open(IDS) if l.strip()]
        by_id = {p.question_id: p for p in probs}
        missing = [q for q in want if q not in by_id]
        if missing:
            raise SystemExit(f"LCB_IDS: {len(missing)} ids not in this release/date range, e.g. {missing[:3]}")
        probs = [by_id[q] for q in want]
    if PROBLEMS:
        val = lambda x: getattr(x, "value", x)  # noqa: E731  (enums)
        index = [{"q": p.question_id, "title": p.question_title, "platform": val(p.platform),
                  "difficulty": val(p.difficulty), "content": p.question_content.strip()} for p in probs]
        with open(PROBLEMS + ".tmp", "w") as f:
            json.dump(index, f, ensure_ascii=False)
        os.replace(PROBLEMS + ".tmp", PROBLEMS)
    return probs


_bm.load_code_generation_dataset = _load_problems  # before scenario_router imports it
_index = []


def _qid(messages):
    """question_id of a request, from problems.json (read once per worker process); None if unknown."""
    if not _index and PROBLEMS and os.path.exists(PROBLEMS):
        _index.extend((p["content"], p["q"]) for p in json.load(open(PROBLEMS)))
    text = "\n".join(m.get("content") or "" for m in messages or [])
    hit = [q for content, q in _index if content and content in text]
    return hit[0] if len(hit) == 1 else None

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
    return getattr(e, "status_code", None) == 402 or any(s in text for s in (
        "insufficient balance", "insufficient_balance", "exceeded_current_quota", "suspended",
        "balance is running low"))  # Kimi: 429 "Your credit balance is running low ..., please recharge"


_run_single_safe.__name__ = "_run_single"  # workers get the bound method pickled by name
_oai.OpenAIRunner._run_single = _run_single_safe

# The SDK's own retries (2 by default, e.g. after a timeout) would resend a request unseen by the log below;
# LCB already retries in _run_single, so turn them off.
_oai.OpenAIRunner.client = _oai.OpenAIRunner.client.with_options(max_retries=0)

# Usage log: one JSON line per API call (question_id, start/end time, first token times, usage, finish reason, the
# answer, or the error), so tools/lcb_usage.py can report latency and tokens, and a later run can recover answers.
_completions = _oai.OpenAIRunner.client.chat.completions
_create = _completions.create


def _log(rec):
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode()
    fd = os.open(USAGE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)  # one O_APPEND write per call, so parallel workers don't interleave lines
    finally:
        os.close(fd)


# Streaming (the default; STREAM=0 turns it off): request a streamed answer and put it back together, so a stalled
# request fails after LCB_TIMEOUT seconds without a token (instead of LCB_TIMEOUT for the whole answer), the time of
# the first token is known, and progress is visible while it runs: every 10 s each worker rewrites
# $LCB_USAGE_LOG.live.<pid> with what it has received so far (cb progress shows it). LCB_STREAM is the old name.
STREAM = os.environ.get("STREAM", os.environ.get("LCB_STREAM", "1")) != "0"
TAIL = 600  # characters of the latest thinking / answer text kept in the live file
_no_stream_options = []  # set once an endpoint has rejected stream_options


def _dump(u):
    return u.model_dump() if hasattr(u, "model_dump") else u


def _open_stream(args, kwargs):
    import openai

    kwargs = dict(kwargs, stream=True)
    if not _no_stream_options:
        try:
            return _create(*args, **dict(kwargs, stream_options={"include_usage": True}))
        except openai.BadRequestError as e:
            if "stream_options" not in str(e) and "include_usage" not in str(e):
                raise
            _no_stream_options.append(1)  # usage then comes from the last chunk, if the endpoint sends it at all
    return _create(*args, **kwargs)


def _create_streamed(*args, **kwargs):
    import types

    import httpx
    import openai

    live = f"{USAGE}.live.{os.getpid()}" if USAGE else None
    q = _qid(kwargs.get("messages"))
    prompt = (kwargs.get("messages") or [{}])[-1].get("content") or ""
    start, first, first_content, last, last_write = time.time(), None, None, None, 0.0
    model, usage, finish, content, reasoning = None, None, None, [], []
    n_reason, n_content, r_tail, c_tail = 0, 0, "", ""
    try:
        for ch in _open_stream(args, kwargs):
            model = ch.model or model
            usage = ch.usage or usage
            for c in ch.choices:
                d = c.delta
                think = getattr(d, "reasoning_content", None) or (getattr(d, "model_extra", None) or {}).get(
                    "reasoning_content")
                if d.content or think:
                    last = time.time()
                    first = first or last
                if d.content:
                    first_content = first_content or last
                    content.append(d.content)
                    n_content += len(d.content)
                    c_tail = (c_tail + d.content)[-TAIL:]
                if think:
                    reasoning.append(think)
                    n_reason += len(think)
                    r_tail = (r_tail + think)[-TAIL:]
                finish = c.finish_reason or finish
                usage = (getattr(c, "model_extra", None) or {}).get("usage") or usage  # Kimi: usage on the choice
            if live and time.time() - last_write > 10:
                last_write = time.time()
                with open(live + ".tmp", "w") as f:
                    json.dump({"q": q, "start": start, "updated": last_write, "first_token": first,
                               "first_content": first_content, "last_token": last, "reasoning_chars": n_reason,
                               "content_chars": n_content, "reasoning_tail": r_tail, "content_tail": c_tail,
                               "prompt": prompt[:2000]}, f, ensure_ascii=False)
                os.replace(live + ".tmp", live)
        if finish is None:  # the server closed the stream without finishing: a cut-off answer, not a real one
            raise openai.APIConnectionError(message="stream ended without a finish_reason",
                                            request=httpx.Request("POST", str(_oai.OpenAIRunner.client.base_url)))
    except Exception as e:
        e.cb_partial = {"q": q, "first_token": first, "first_content": first_content, "reasoning_chars": n_reason,
                        "content_chars": n_content, "usage": _dump(usage) if usage else None}
        if isinstance(e, openai.OpenAIError):
            raise
        if isinstance(e, httpx.TimeoutException):  # raised while reading the stream; LCB only retries openai errors
            raise openai.APITimeoutError(request=e.request) from e
        if isinstance(e, httpx.HTTPError):
            raise openai.APIConnectionError(request=getattr(e, "request", None) or httpx.Request("POST", "")) from e
        raise
    finally:
        if live and os.path.exists(live):
            os.remove(live)
    msg = types.SimpleNamespace(content="".join(content))
    return types.SimpleNamespace(model=model, usage=usage, q=q, first_token=first, first_content=first_content,
                                 reasoning_chars=n_reason,
                                 choices=[types.SimpleNamespace(finish_reason=finish, message=msg)])


def _create_checked(*args, **kwargs):
    rec = {"start": time.time(), "stream": STREAM, "messages": kwargs.get("messages")}
    try:
        r = (_create_streamed if STREAM else _create)(*args, **kwargs)
    except Exception as e:
        if _is_out_of_balance(e):
            _broke.append(1)
        if USAGE:
            rec.update(getattr(e, "cb_partial", None) or {"q": _qid(kwargs.get("messages"))})
            rec.update(end=time.time(), error=repr(e)[:500])
            _log(rec)
        raise
    if USAGE:
        rec.update(q=r.q if STREAM else _qid(kwargs.get("messages")), end=time.time(), model=r.model,
                   usage=_dump(r.usage) if r.usage else None, finish=[c.finish_reason for c in r.choices],
                   chars=[len(c.message.content or "") for c in r.choices],
                   content=[c.message.content or "" for c in r.choices])
        if STREAM:
            rec.update(first_token=r.first_token, first_content=r.first_content, reasoning_chars=r.reasoning_chars)
        _log(rec)
    return r


_completions.create = _create_checked

from lcb_runner.runner import main as lcb_main  # noqa: E402  (after registering)


def _recover_from_usage_log():
    """Put answers logged in $LCB_USAGE_LOG into LCB's output file, so --continue_existing skips those problems.

    LCB writes its output file only after the last problem, so a run that is killed or crashes loses every answer;
    the usage log has them. Only problems with no non-empty answer in the output file are filled in.
    """
    from lcb_runner.runner.parser import get_args
    from lcb_runner.runner.scenario_router import build_prompt_benchmark, combine_results
    from lcb_runner.utils.path_utils import get_output_path

    answers = {}  # prompt text -> answers, last successful call wins
    for line in open(USAGE):
        rec = json.loads(line)
        if rec.get("content") and any(rec["content"]):
            answers["\n".join(m.get("content") or "" for m in rec["messages"])] = rec["content"]
    if not answers:
        return
    args = get_args()
    model = lm_styles.LanguageModelStore[args.model]
    benchmark, _ = build_prompt_benchmark(args)
    path = get_output_path(model.model_repr, args)
    old = json.load(open(path)) if os.path.exists(path) else []
    have = {r["question_id"] for r in old if any(r["output_list"])}
    new = []
    for p in benchmark:
        if p.question_id in have:
            continue
        hit = [a for prompt, a in answers.items() if p.question_content.strip() in prompt]
        if hit:
            (outputs, codes), = combine_results(args.scenario, [hit[-1]], model, args.cot_code_execution)
            new.append(p.insert_output(outputs, codes))
    if new:
        ids = {r["question_id"] for r in new}
        json.dump([r for r in old if r["question_id"] not in ids] + new, open(path, "w"), indent=4)
        print(f"recovered {len(new)} answers from {USAGE}")


if __name__ == "__main__":  # the runner's worker processes are spawned and re-import this file
    sys.argv = ["lcb_runner.runner.main", "--model", name] + sys.argv[1:]
    if USAGE and os.path.exists(USAGE):
        _recover_from_usage_log()
    lcb_main.main()
