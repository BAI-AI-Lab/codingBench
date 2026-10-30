"""Generate answers for the ladder test set with any OpenAI-compatible model (cb ladder runs this, then judges).

  python ladder_run.py --out <run dir> [--manifest samples/ladder.json] [--tiers L1,L2,L3,L4,L5]
                       [--n L1=1,L2=1,L3=3,L4=3,L5=1] [--only pid,...] [--smoke]

Environment: MODEL, OPENAI_BASE_URL, OPENAI_API_KEY; MAX_TOKENS (default "none" = no limit), WORKERS (parallel
requests, 16), STREAM (1), LADDER_TIMEOUT (streamed: seconds without a token before a retry, 300; STREAM=0: seconds
for the whole answer, 1800), LADDER_OMIT (request fields to leave out, e.g. Kimi: temperature,top_p), TEMPERATURE
(0.2, LiveCodeBench's), RETRIES (3).

Writes, like cb livecodebench does: problems.json (what cb progress shows), usage.jsonl (one line per API call: times,
first-token times, tokens, finish reason, answer or error; same fields as lcb_run.py, so cb progress / cb usage read
it), and answers.jsonl (q = <pid>#<sample>, the extracted code). A re-run skips samples that already have an
answer in usage.jsonl, so an interrupted run resumes without repeating paid calls. To pause cleanly, touch
<run dir>/STOP: no new request starts, the ones in flight finish and are kept, and the run exits with status 4.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import ladder_lib as L  # noqa: E402

TAIL = 600
# LADDER_MAX_SECONDS: a streamed request longer than this is cut off and logged as finish "timeout" (not retried);
# the server returns no usage for a cut stream, so its tokens are estimated from the characters streamed so far
# (LADDER_CHARS_PER_TOKEN: 3.57 measured on MiniMax-M3.1-Flash completed calls; median, 10th-90th percentile 3.0-3.9)
CHARS_PER_TOKEN = float(os.environ.get("LADDER_CHARS_PER_TOKEN") or 3.57)
# LADDER_CUT_IS_TIMEOUT: a stream the server drops after at least this many seconds also counts as a timeout (the model
# did not finish), instead of an error that is retried. LADDER_REDO_TIMEOUTS=1 asks timed-out samples again (e.g. with a
# longer LADDER_MAX_SECONDS); whatever that attempt gives is the sample's answer.
_broke = []
_write = threading.Lock()


def log(path, rec):
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode()
    with _write:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)


def out_of_balance(e):
    text = repr(e).lower()
    return getattr(e, "status_code", None) == 402 or any(s in text for s in (
        "insufficient balance", "insufficient_balance", "exceeded_current_quota", "suspended",
        "balance is running low"))


def text_of(messages):
    """The last message's text (the text parts of a multimodal one), for the live file."""
    c = messages[-1]["content"]
    return (c if isinstance(c, str) else "\n".join(p.get("text", "") for p in c if p.get("type") == "text"))[:2000]


def call(client, model, messages, args, usage_path, q, logged=None):
    """One request (streamed unless STREAM=0); returns the usage-log record (content or error). `logged` is what the
    logs keep of the messages (default: the messages as sent), e.g. with the images replaced by their file names."""
    import openai
    kw = {"model": model, "messages": messages, "temperature": args.temperature, "top_p": 0.95}
    if args.max_tokens:
        kw["max_tokens"] = args.max_tokens
    if getattr(args, "reasoning_effort", None):  # REASONING_EFFORT, e.g. low / high / max (MiniMax, Kimi, DeepSeek)
        kw["extra_body"] = {"reasoning_effort": args.reasoning_effort}
    for k in args.omit:
        kw.pop(k, None)
    logged = messages if logged is None else logged
    rec = {"q": q, "start": time.time(), "stream": args.stream, "messages": logged}
    live = f"{usage_path}.live.{os.getpid()}-{threading.get_ident()}"
    first = first_content = None
    n_reason = n_content = 0
    usage = finish = mdl = None
    try:
        if not args.stream:
            r = client.chat.completions.create(**kw)
            c = r.choices[0]
            content, finish, mdl = c.message.content or "", c.finish_reason, r.model
            usage = r.usage.model_dump() if r.usage else None
        else:
            try:
                stream = client.chat.completions.create(**kw, stream=True, stream_options={"include_usage": True})
            except openai.BadRequestError as e:
                if "stream_options" not in str(e) and "include_usage" not in str(e):
                    raise
                stream = client.chat.completions.create(**kw, stream=True)
            parts, r_tail, c_tail, last_write = [], "", "", 0.0
            limit = float(os.environ.get("LADDER_MAX_SECONDS") or 0)
            timed_out = False
            for ch in stream:
                if limit and time.time() - rec["start"] > limit:
                    timed_out = True
                    break
                mdl = ch.model or mdl
                if ch.usage:
                    usage = ch.usage.model_dump()
                for c in ch.choices:
                    d = c.delta
                    think = getattr(d, "reasoning_content", None) or (getattr(d, "model_extra", None) or {}).get("reasoning_content")
                    now = time.time()
                    if d.content or think:
                        first = first or now
                    if d.content:
                        first_content = first_content or now
                        parts.append(d.content)
                        n_content += len(d.content)
                        c_tail = (c_tail + d.content)[-TAIL:]
                    if think:
                        n_reason += len(think)
                        r_tail = (r_tail + think)[-TAIL:]
                    finish = c.finish_reason or finish
                    u = (getattr(c, "model_extra", None) or {}).get("usage")
                    usage = u or usage
                if time.time() - last_write > 10:
                    last_write = time.time()
                    with open(live + ".tmp", "w") as f:
                        json.dump({"q": q, "start": rec["start"], "updated": last_write, "first_token": first,
                                   "first_content": first_content, "reasoning_chars": n_reason,
                                   "content_chars": n_content, "reasoning_tail": r_tail, "content_tail": c_tail,
                                   "prompt": text_of(logged)}, f, ensure_ascii=False)
                    os.replace(live + ".tmp", live)
            if timed_out:
                finish = "timeout"
                stream.close()
            elif finish is None:
                raise RuntimeError("stream ended without a finish_reason")
            content = "".join(parts)
        if finish == "timeout" and not usage:
            usage = {"completion_tokens": round((n_reason + n_content) / CHARS_PER_TOKEN), "prompt_tokens": 0, "estimated": True}
        rec.update(end=time.time(), model=mdl, usage=usage, finish=[finish], chars=[len(content)], content=[content],
                   first_token=first, first_content=first_content, reasoning_chars=n_reason)
    except Exception as e:  # noqa: BLE001  (logged and retried by the caller)
        cut_after = float(os.environ.get("LADDER_CUT_IS_TIMEOUT") or 0)
        if cut_after and args.stream and time.time() - rec["start"] >= cut_after and not out_of_balance(e):
            # the server dropped a stream that had already run this long: the model did not finish in time
            rec.update(end=time.time(), model=mdl, finish=["timeout"], chars=[0], content=[""], first_token=first,
                       first_content=first_content, reasoning_chars=n_reason, content_chars=n_content, cut=repr(e)[:300],
                       usage=usage or {"completion_tokens": round((n_reason + n_content) / CHARS_PER_TOKEN),
                                       "prompt_tokens": 0, "estimated": True})
        else:
            if out_of_balance(e):
                _broke.append(1)
            rec.update(end=time.time(), error=repr(e)[:500], first_token=first, first_content=first_content,
                       reasoning_chars=n_reason, content_chars=n_content, usage=usage)
    finally:
        if os.path.exists(live):
            os.remove(live)
    log(usage_path, rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    default = os.path.join(L.CB, "samples", "ladder.json")  # the committed list; before it exists, the one just built
    ap.add_argument("--manifest", default=default if os.path.exists(default) else os.path.join(L.DATA, "ladder.json"))
    ap.add_argument("--tiers", default=",".join(L.TIERS))
    ap.add_argument("--n", default=os.environ.get("LADDER_N", "L1=1,L2=1,L3=3,L4=3,L5=1"))
    ap.add_argument("--only", default="")
    ap.add_argument("--smoke", action="store_true", help="the first problem of every tier, one sample")
    a = ap.parse_args()
    a.temperature = float(os.environ.get("TEMPERATURE", "0.2"))
    mt = os.environ.get("MAX_TOKENS", "none")
    a.max_tokens = None if mt.lower() in ("none", "0", "") else int(mt)
    a.stream = os.environ.get("STREAM", "1") != "0"
    a.omit = [k.strip() for k in (os.environ.get("LADDER_OMIT") or os.environ.get("LCB_OMIT") or "").split(",") if k.strip()]
    timeout = float(os.environ.get("LADDER_TIMEOUT") or (300 if a.stream else 1800))
    retries = int(os.environ.get("RETRIES", "3"))
    model = os.environ["MODEL"]
    import httpx
    import openai
    client = openai.OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"], max_retries=0,
                           timeout=httpx.Timeout(timeout, connect=30.0))
    n_of = dict(x.split("=") for x in a.n.split(","))
    tiers = a.tiers.split(",")
    only = set(filter(None, a.only.split(",")))
    m = json.load(open(a.manifest))
    jobs = []
    for t in tiers:
        pids = m["tiers"].get(t, [])
        if only:
            pids = [p for p in pids if p in only]
        if a.smoke:
            pids = pids[:1]
        for p in pids:
            for k in range(1 if a.smoke else int(n_of.get(t, 1))):
                jobs.append((p, k))
    os.makedirs(a.out, exist_ok=True)
    usage_path = os.path.join(a.out, "usage.jsonl")
    metas = {p: L.load_meta(p) for p in {p for p, _ in jobs}}
    stmts = {p: open(os.path.join(L.PROBLEMS, p, "statement.md")).read().strip() for p in metas}
    index = [{"q": f"{p}#{k}", "title": metas[p]["title"], "platform": metas[p]["source"], "difficulty": metas[p]["tier"],
              "content": stmts[p][:4000]} for p, k in jobs]
    json.dump(index, open(os.path.join(a.out, "problems.json"), "w"), ensure_ascii=False)
    json.dump({"model": model, "name": os.environ.get("MODEL_NAME") or model, "manifest": a.manifest, "tiers": tiers, "n": n_of, "smoke": a.smoke,
               "temperature": a.temperature, "max_tokens": a.max_tokens, "started": time.time()},
              open(os.path.join(a.out, "run.json"), "w"), indent=1)
    have = {}
    if os.path.exists(usage_path):
        for l in open(usage_path):
            r = json.loads(l)
            if r.get("content") and r["content"][0].strip() and (r.get("finish") or [None])[0] != "timeout":
                have[r["q"]] = r
    ans_path = os.path.join(a.out, "answers.jsonl")
    # a sample whose retries all failed (finish "error", no code) is asked again on the next run
    last = {}
    for r in (map(json.loads, open(ans_path)) if os.path.exists(ans_path) else []):
        last[r["q"]] = r  # the last answer per sample counts (as in the judge)
    redo = os.environ.get("LADDER_REDO_TIMEOUTS") == "1"
    done = {q for q, r in last.items() if r.get("finish") != "error" and not (redo and r.get("finish") == "timeout")}

    def answer(rec, p, k):
        timed_out = (rec.get("finish") or [None])[0] == "timeout"  # a cut answer is not code: it is a failure
        code = L.extract_code(rec["content"][0], metas[p]["lang"]) if rec.get("content") and not timed_out else ""
        r = {"q": f"{p}#{k}", "pid": p, "k": k, "tier": metas[p]["tier"], "lang": metas[p]["lang"], "code": code,
             "finish": (rec.get("finish") or [None])[0], "code_hash": hashlib.sha1(code.encode()).hexdigest()[:12]}
        log(ans_path, r)

    for p, k in jobs:  # answers logged by an earlier, interrupted run
        q = f"{p}#{k}"
        if q in have and q not in done:
            answer(have[q], p, k)
            done.add(q)
    todo = [(p, k) for p, k in jobs if f"{p}#{k}" not in done]
    print(f"{len(jobs)} samples, {len(jobs) - len(todo)} already answered, {len(todo)} to ask {model}")

    stop_file = os.path.join(a.out, "STOP")  # touch <run dir>/STOP: no new requests, the ones in flight finish

    def one(job):
        p, k = job
        if os.path.exists(stop_file):
            return p, k, None
        system, user = L.prompt(metas[p], stmts[p])
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        rec = None
        for i in range(retries + 1):
            if _broke:
                break
            rec = call(client, model, messages, a, usage_path, f"{p}#{k}")
            if "error" not in rec:
                break
            time.sleep(min(60, 5 * 2 ** i))
        rec = rec if rec and "error" not in rec else {"content": [""], "finish": ["error"]}
        answer(rec, p, k)
        return p, k, rec

    with concurrent.futures.ThreadPoolExecutor(int(os.environ.get("WORKERS", "16"))) as ex:
        for p, k, rec in ex.map(one, todo):
            if rec is None:
                continue
            u = rec.get("usage") or {}
            print(f"{p}#{k:<3} {metas[p]['tier']} finish={rec.get('finish', ['?'])[0]} "
                  f"out_tokens={u.get('completion_tokens', '-')} {time.strftime('%H:%M:%S')}", flush=True)
    if _broke:
        print("STOPPED: the API account is out of balance; answered samples are kept, re-run to continue")
        sys.exit(3)
    if os.path.exists(stop_file):
        os.remove(stop_file)
        print("PAUSED (STOP file): answered samples are kept, re-run to continue")
        sys.exit(4)


if __name__ == "__main__":
    main()
