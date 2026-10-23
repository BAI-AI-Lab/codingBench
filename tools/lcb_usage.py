"""Latency and token report for a LiveCodeBench run made with LCB_USAGE_LOG (cb sets it to <run dir>/usage.jsonl).

  python lcb_usage.py <run dir> [--out usage.md] [--price-in 0.3 --price-hit 0.006 --price-out 1.2]

Prices are per million tokens (any currency); without them no cost is shown. Each API call is matched to its
problem by the problem statement inside the prompt. Latency is per call, measured while WORKERS calls ran in
parallel, so it includes any queueing on the provider's side.
"""
import argparse
import glob
import json
import os
import statistics

ap = argparse.ArgumentParser()
ap.add_argument("run_dir")
ap.add_argument("--out")
ap.add_argument("--price-in", type=float, help="input price per 1M tokens (cache miss)")
ap.add_argument("--price-hit", type=float, help="input price per 1M tokens (cache hit); default = --price-in")
ap.add_argument("--price-out", type=float, help="output price per 1M tokens (reasoning included)")
a = ap.parse_args()

f = glob.glob(os.path.join(a.run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
if len(f) != 1:
    raise SystemExit(f"expected one *_eval_all.json under {a.run_dir}/output, found {len(f)}")
rows = json.load(open(f[0]))
calls = [json.loads(l) for l in open(os.path.join(a.run_dir, "usage.jsonl")) if l.strip()]
model = os.path.basename(os.path.dirname(f[0]))


def prompt_text(c):
    return "\n".join(m.get("content") or "" for m in c.get("messages") or [])


def problem_of(c):
    text = prompt_text(c)
    hit = [r["question_id"] for r in rows if r["question_content"].strip() in text]
    return hit[0] if len(hit) == 1 else None


def tokens(u):
    """(prompt, cache hit, completion, reasoning) from DeepSeek- or OpenAI/Kimi-style usage."""
    u = u or {}
    hit = u.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("cached_tokens") or 0
    reason = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return u.get("prompt_tokens") or 0, hit, u.get("completion_tokens") or 0, reason


ok = [c for c in calls if "error" not in c]
err = [c for c in calls if "error" in c]
by_q = {}
for c in ok:
    q = problem_of(c)
    if q is None:
        raise SystemExit(f"could not match a call to exactly one problem (start {c['start']})")
    by_q.setdefault(q, []).append(c)
missing = [r["question_id"] for r in rows if r["question_id"] not in by_q]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def fmt_tok(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k"


lat = {q: cs[-1]["end"] - cs[-1]["start"] for q, cs in by_q.items()}  # the answer that was kept
tok = {q: tokens(cs[-1].get("usage")) for q, cs in by_q.items()}
tot = [sum(tokens(c.get("usage"))[i] for c in ok) for i in range(4)]  # every billed call, incl. superseded ones
wall = max(c["end"] for c in calls) - min(c["start"] for c in calls)
speed = [tok[q][2] / lat[q] for q in by_q if lat[q] > 0 and tok[q][2]]
passed = {r["question_id"]: bool(r["graded_list"][0]) for r in rows}
diff = {r["question_id"]: r["difficulty"] for r in rows}

L = [f"# LiveCodeBench 延迟和 token：{model}", "",
     f"- 题目：{len(rows)}，通过 {sum(passed.values())}（pass@1 {100 * sum(passed.values()) / len(rows):.1f}%）",
     f"- 总耗时：{wall / 60:.1f} 分钟（第一个请求发出到最后一个返回）",
     f"- API 调用：成功 {len(ok)}，出错 {len(err)}" + (f"（{len(by_q)} 题有成功的回答）" if missing else ""),
     f"- token：输入 {fmt_tok(tot[0])}（其中缓存命中 {fmt_tok(tot[1])}），输出 {fmt_tok(tot[2])}"
     + (f"（其中思考 {fmt_tok(tot[3])}）" if tot[3] else "")]
if missing:
    L.append(f"- 没有成功调用记录的题（请求都失败了、余额不足没发请求，或续跑时沿用了旧回答）：{', '.join(missing)}")
if a.price_in is not None and a.price_out is not None:
    hit_price = a.price_hit if a.price_hit is not None else a.price_in
    cost = ((tot[0] - tot[1]) * a.price_in + tot[1] * hit_price + tot[2] * a.price_out) / 1e6
    L.append(f"- 费用：约 {cost:.2f}（单价 输入 {a.price_in} / 缓存命中 {hit_price} / 输出 {a.price_out}，每百万 token）")
if lat:
    v = list(lat.values())
    L += ["", "## 每题延迟（秒，并行跑时测得）", "",
          "| 平均 | 中位数 | P90 | 最长 |", "|---:|---:|---:|---:|",
          f"| {statistics.mean(v):.0f} | {statistics.median(v):.0f} | {pct(v, 90):.0f} | {max(v):.0f} |"]
if speed:
    L.append(f"\n输出速度（每题输出 token ÷ 延迟）：中位数 {statistics.median(speed):.0f} token/秒")

L += ["", "## 按难度", "", "| 难度 | 题数 | 通过 | 延迟中位数（秒） | 输出 token 平均 | 输出 token 最多 |",
      "|---|---:|---:|---:|---:|---:|"]
for d in ["easy", "medium", "hard"]:
    qs = [q for q in passed if diff[q] == d]
    if not qs:
        continue
    have = [q for q in qs if q in by_q]
    outs = [tok[q][2] for q in have]
    L.append(f"| {d} | {len(qs)} | {sum(passed[q] for q in qs)} | "
             + (f"{statistics.median(lat[q] for q in have):.0f} | {fmt_tok(statistics.mean(outs))} | {fmt_tok(max(outs))} |"
                if have else "— | — | — |"))

L += ["", "## 每题", "", "| 题目 | 难度 | 通过 | 延迟（秒） | 输出 token | 思考 token | 结束原因 |",
      "|---|---|:-:|---:|---:|---:|---|"]
for r in sorted(rows, key=lambda r: -lat.get(r["question_id"], 0)):
    q = r["question_id"]
    if q in by_q:
        _, _, out, reason = tok[q]
        fin = ",".join(str(x) for x in by_q[q][-1].get("finish") or [])
        L.append(f"| {q} | {diff[q]} | {'✓' if passed[q] else '✗'} | {lat[q]:.0f} | {out} | {reason or '—'} | {fin} |")
    else:
        L.append(f"| {q} | {diff[q]} | {'✓' if passed[q] else '✗'} | — | — | — | — |")
if err:
    L += ["", "## 出错的调用", ""] + [f"- {c['error'][:200]}" for c in err[:20]]

text = "\n".join(L) + "\n"
if a.out:
    open(a.out, "w").write(text)
print(text, end="")
