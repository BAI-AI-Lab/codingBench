"""Progress of a LiveCodeBench run, while it is going or after: how many problems have an answer, the errors, and
every request in flight with its elapsed time and the thinking / answer received so far.

  python lcb_progress.py <run dir> [--watch 30] [--text]

Reads <run dir>/problems.json and usage.jsonl, and the usage.jsonl.live.<pid> files that each worker rewrites every
10 s while a streamed request (the default) is open. Runs made before problems.json existed fall back to matching
the prompt against the problems of _eval_all.json.
"""
import argparse
import glob
import json
import os
import sys
import time


def load(run_dir):
    path = os.path.join(run_dir, "problems.json")
    if os.path.exists(path):
        return json.load(open(path))
    f = glob.glob(os.path.join(run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if f:
        return [{"q": r["question_id"], "title": r.get("question_title", ""), "platform": r["platform"],
                 "difficulty": r["difficulty"], "content": r["question_content"].strip()} for r in json.load(open(f[0]))]
    return []


def matcher(problems):
    def qid(rec):
        if rec.get("q"):
            return rec["q"]
        text = rec.get("prompt") or "\n".join(m.get("content") or "" for m in rec.get("messages") or [])
        hit = [p["q"] for p in problems if p["content"] and p["content"][:300] in text]
        return hit[0] if len(hit) == 1 else "?"
    return qid


def ago(t, now):
    s = int(now - t)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def kchars(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def report(run_dir, text):
    now = time.time()
    problems = load(run_dir)
    qid = matcher(problems)
    meta = {p["q"]: p for p in problems}
    usage = os.path.join(run_dir, "usage.jsonl")
    calls = [json.loads(l) for l in open(usage) if l.strip()] if os.path.exists(usage) else []
    answered, errors = {}, []
    for c in calls:
        q = qid(c)
        if "error" in c:
            errors.append((q, c))
        elif any((x or "").strip() for x in c.get("content") or []):
            answered[q] = c
    live = []
    for f in glob.glob(os.path.join(run_dir, "usage.jsonl.live.*")):
        try:
            r = json.load(open(f))
        except (OSError, ValueError):
            continue  # being replaced right now
        pid = f.rsplit(".", 1)[-1]
        if pid.isdigit() and not os.path.exists(f"/proc/{pid}"):
            continue  # left behind by a worker that was killed
        live.append((qid(r), r))
    total = len(problems) or "?"
    out_tok = sum(((c.get("usage") or {}).get("completion_tokens") or 0) for c in calls if "error" not in c)
    L = [f"{run_dir}  {time.strftime('%F %T')}",
         f"answered {len(answered)}/{total} · in flight {len(live)} · errors {len(errors)} · output tokens {out_tok:,}"]
    if live:
        L += ["", "in flight (elapsed · thinking / answer characters received · last token):"]
        for q, r in sorted(live, key=lambda x: x[1]["start"]):
            d = meta.get(q, {}).get("difficulty", "")
            last = r.get("last_token")
            L.append(f"  {q:<10} {d:<6} {ago(r['start'], now):>8}   thinking {kchars(r.get('reasoning_chars', 0)):>7}"
                     f"   answer {kchars(r.get('content_chars', 0)):>6}   "
                     + (f"{ago(last, now)} ago" if last else "no token yet"))
            if text:
                for k, name in (("reasoning_tail", "thinking"), ("content_tail", "answer")):
                    if r.get(k):
                        L.append(f"      {name}: …" + " ".join(r[k].split())[-300:])
    if answered:
        L += ["", "answered (latest 5: seconds · output tokens · finish reason):"]
        for q, c in sorted(answered.items(), key=lambda x: -x[1]["end"])[:5]:
            tok = (c.get("usage") or {}).get("completion_tokens")
            L.append(f"  {q:<10} {c['end'] - c['start']:>7.0f}   {tok if tok is not None else '—':>7}   "
                     + ",".join(str(x) for x in c.get("finish") or []))
    if errors:
        L += ["", "errors (latest 3):"]
        for q, c in errors[-3:]:
            L.append(f"  {time.strftime('%H:%M:%S', time.localtime(c['end']))} {q:<10} {c['error'][:120]}")
    left = [p["q"] for p in problems if p["q"] not in answered and p["q"] not in {q for q, _ in live}]
    if left and len(left) <= 12:
        L += ["", "not answered yet: " + ", ".join(left)]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--watch", type=float, help="refresh every N seconds until interrupted")
    ap.add_argument("--text", action="store_true", help="also show the latest thinking / answer text of each request")
    a = ap.parse_args()
    if not os.path.isdir(a.run_dir):
        raise SystemExit(f"no such run dir: {a.run_dir}")
    while True:
        text = report(a.run_dir, a.text)
        if a.watch and sys.stdout.isatty():
            sys.stdout.write("\033[H\033[J")
        print(text, flush=True)
        if not a.watch:
            return
        try:
            time.sleep(a.watch)
        except KeyboardInterrupt:
            return
        if not sys.stdout.isatty():
            print()


if __name__ == "__main__":
    main()
