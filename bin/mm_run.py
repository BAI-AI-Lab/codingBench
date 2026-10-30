"""Answer the multimodal ladder (cb mm) with any OpenAI-compatible model that takes images; mm_report.py scores.

  python mm_run.py --out <run dir> [--manifest samples/mm.json] [--caps reasoning,charts] [--k 4] [--only id,...]
                   [--smoke]

Environment: MODEL, OPENAI_BASE_URL, OPENAI_API_KEY; MAX_TOKENS (default "none" = no limit; thinking counts toward
it, so a small limit gives empty answers), REASONING_EFFORT (sent as reasoning_effort when set, e.g. MiniMax / Kimi
low|high|max), MM_TEMPERATURE (default: not sent, so every model runs at its vendor's default; Kimi K3 rejects other
values and MiniMax ignores them), MM_DETAIL (image detail, e.g. high; default not sent), MM_OMIT (more request fields
to leave out), WORKERS (8), STREAM (1), MM_TIMEOUT (streamed: seconds without a token before a retry, 300),
LADDER_MAX_SECONDS (a request longer than this is cut off and counts as a timeout), RETRIES (3).

Like cb ladder, it writes problems.json, run.json, usage.jsonl (one line per API call; images logged by file name
only) and answers.jsonl (q = <item id>#<sample>, the reply). A re-run asks only what is missing; touch <run dir>/STOP
to pause (exit 4); an account out of balance stops the run (exit 3).
"""
import argparse
import concurrent.futures
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import ladder_run as R  # noqa: E402  (the API call, its logging and the out-of-balance stop)
import mm_lib as M  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    default = os.path.join(ROOT, "samples", "mm.json")
    ap.add_argument("--manifest", default=default if os.path.exists(default) else os.path.join(M.DATA, "mm.json"))
    ap.add_argument("--caps", default="")
    ap.add_argument("--k", type=int, default=int(os.environ.get("MM_K", "4")), help="samples per item")
    ap.add_argument("--only", default="")
    ap.add_argument("--smoke", action="store_true", help="the first item of every capability, one sample")
    a = ap.parse_args()
    t = os.environ.get("MM_TEMPERATURE", "")
    a.temperature = float(t) if t else None
    mt = os.environ.get("MAX_TOKENS", "none")
    a.max_tokens = None if mt.lower() in ("none", "0", "") else int(mt)
    a.reasoning_effort = os.environ.get("REASONING_EFFORT") or None
    a.stream = os.environ.get("STREAM", "1") != "0"
    a.omit = [k.strip() for k in os.environ.get("MM_OMIT", "").split(",") if k.strip()]
    if a.temperature is None:
        a.omit += ["temperature", "top_p"]
    detail = os.environ.get("MM_DETAIL") or None
    timeout = float(os.environ.get("MM_TIMEOUT") or (300 if a.stream else 1800))
    retries = int(os.environ.get("RETRIES", "3"))
    model = os.environ["MODEL"]
    import httpx
    import openai
    client = openai.OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"], max_retries=0,
                           timeout=httpx.Timeout(timeout, connect=30.0))
    m = M.load_manifest(a.manifest)
    caps = [c for c in (a.caps.split(",") if a.caps else M.CAPS) if c in m["capabilities"]]
    only = set(filter(None, a.only.split(",")))
    jobs = []
    for c in caps:
        ids = [i for i in m["capabilities"][c] if not only or i in only]
        for iid in ids[:1] if a.smoke else ids:
            for k in range(1 if a.smoke else a.k):
                jobs.append((iid, k))
    os.makedirs(a.out, exist_ok=True)
    usage_path = os.path.join(a.out, "usage.jsonl")
    items = {i: M.load_item(i) for i in {i for i, _ in jobs}}
    index = [{"q": f"{i}#{k}", "title": i, "platform": items[i]["source"], "difficulty": items[i]["tier"],
              "content": M.prompt_text(items[i])[:4000]} for i, k in jobs]
    json.dump(index, open(os.path.join(a.out, "problems.json"), "w"), ensure_ascii=False)
    json.dump({"model": model, "name": os.environ.get("MODEL_NAME") or model, "manifest": a.manifest,
               "version": m.get("version"), "caps": caps, "k": 1 if a.smoke else a.k, "smoke": a.smoke,
               "temperature": a.temperature, "max_tokens": a.max_tokens, "reasoning_effort": a.reasoning_effort,
               "detail": detail, "omit": a.omit, "started": time.time()},
              open(os.path.join(a.out, "run.json"), "w"), indent=1)
    have = {}
    if os.path.exists(usage_path):
        for line in open(usage_path):
            r = json.loads(line)
            if r.get("content") and r["content"][0].strip() and (r.get("finish") or [None])[0] != "timeout":
                have[r["q"]] = r
    ans_path = os.path.join(a.out, "answers.jsonl")
    last = {}
    for r in (map(json.loads, open(ans_path)) if os.path.exists(ans_path) else []):
        last[r["q"]] = r
    done = {q for q, r in last.items() if r.get("finish") != "error"}

    def answer(rec, iid, k):
        it = items[iid]
        finish = (rec.get("finish") or [None])[0]
        text = rec["content"][0] if rec.get("content") and finish != "timeout" else ""
        R.log(ans_path, {"q": f"{iid}#{k}", "id": iid, "k": k, "capability": it["capability"], "tier": it["tier"],
                         "source": it["source"], "finish": finish, "text": text})

    for iid, k in jobs:  # answers logged by an earlier, interrupted run
        q = f"{iid}#{k}"
        if q in have and q not in done:
            answer(have[q], iid, k)
            done.add(q)
    todo = [(i, k) for i, k in jobs if f"{i}#{k}" not in done]
    print(f"{len(jobs)} samples, {len(jobs) - len(todo)} already answered, {len(todo)} to ask {model}")
    stop_file = os.path.join(a.out, "STOP")

    def one(job):
        iid, k = job
        if os.path.exists(stop_file):
            return iid, k, None
        msgs, logged = M.messages(items[iid], detail)
        rec = None
        for i in range(retries + 1):
            if R._broke:
                break
            rec = R.call(client, model, msgs, a, usage_path, f"{iid}#{k}", logged=logged)
            if "error" not in rec:
                break
            time.sleep(min(60, 5 * 2 ** i))
        rec = rec if rec and "error" not in rec else {"content": [""], "finish": ["error"]}
        answer(rec, iid, k)
        return iid, k, rec

    with concurrent.futures.ThreadPoolExecutor(int(os.environ.get("WORKERS", "8"))) as ex:
        for iid, k, rec in ex.map(one, todo):
            if rec is None:
                continue
            u = rec.get("usage") or {}
            print(f"{iid}#{k:<2} {items[iid]['capability']} finish={rec.get('finish', ['?'])[0]} "
                  f"out_tokens={u.get('completion_tokens', '-')} {time.strftime('%H:%M:%S')}", flush=True)
    if R._broke:
        print("STOPPED: the API account is out of balance; answered samples are kept, re-run to continue")
        sys.exit(3)
    if os.path.exists(stop_file):
        os.remove(stop_file)
        print("PAUSED (STOP file): answered samples are kept, re-run to continue")
        sys.exit(4)


if __name__ == "__main__":
    main()
