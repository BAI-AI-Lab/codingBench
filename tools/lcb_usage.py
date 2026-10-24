"""Latency, token and cost report for a LiveCodeBench run made with LCB_USAGE_LOG (cb sets it to <run dir>/usage.jsonl).

  python lcb_usage.py <run dir> [--out usage.md] [--price-in 0.3 --price-hit 0.006 --price-out 1.2
                       [--price-off-in 0.15 --price-off-hit 0.003 --price-off-out 0.6 --peak-hours-utc 1-4,6-10]]

Writes <run dir>/usage.md (or --out) and usage.json (the same numbers for other tools) and prints the report.
Prices are per million tokens (any currency; defaults from $PRICE_IN, $PRICE_HIT, $PRICE_OUT, $PRICE_OFF_IN, ...,
$PEAK_HOURS_UTC); without them no cost is shown. With off-peak prices, a call started on a weekday in the peak
hours (UTC) is billed at the --price-* rates and any other call at the --price-off-* rates (DeepSeek: peak
01:00-04:00 and 06:00-10:00 UTC, Monday to Friday). Each call is matched to its problem by the question_id it was logged with, or for older logs by the problem
statement inside the prompt. Passed means the re-judged verdict of <run dir>/rejudge.jsonl (cb rejudge) when it
exists, else LCB's own. Latency is per call, measured while WORKERS calls ran in parallel, so it includes any
queueing on the provider's side; first-token times exist only for streamed calls (the default).
"""
import argparse
import datetime
import glob
import json
import os
import statistics

LEGEND = "↑ 越大越好，↓ 越小越好；没有箭头的只作描述。"
DIFFS = ("easy", "medium", "hard")


def tokens(u):
    """(prompt, cache hit, completion, reasoning) from DeepSeek- or OpenAI/Kimi-style usage."""
    u = u or {}
    hit = u.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("cached_tokens") or 0
    reason = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return u.get("prompt_tokens") or 0, hit, u.get("completion_tokens") or 0, reason


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def covered(intervals):
    """Seconds covered by the union of (start, end) intervals."""
    total, end = 0.0, None
    for s, e in sorted(intervals):
        if end is None or s > end:
            total, end = total + e - s, e
        elif e > end:
            total, end = total + e - end, e
    return total


def is_peak(t, hours):
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return d.weekday() < 5 and any(a <= d.hour < b for a, b in hours)


def call_cost(c, prices):
    """Cost of one call; prices = {"in", "hit", "out"[, "off": {"in", "hit", "out"}, "peak_hours": [(a, b)]]}."""
    p = prices if "off" not in prices or is_peak(c["start"], prices["peak_hours"]) else prices["off"]
    t = tokens(c.get("usage"))
    return ((t[0] - t[1]) * p["in"] + t[1] * p["hit"] + t[2] * p["out"]) / 1e6


def fmt_tok(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k"


def stats(v):
    return {"n": len(v), "mean": statistics.mean(v), "median": statistics.median(v), "p90": pct(v, 90), "max": max(v)} \
        if v else None


def analyze(rows, calls, passed, prices=None):
    """rows: LCB's _eval_all.json; calls: usage.jsonl records; passed: {question_id: bool}. Returns a summary dict."""
    def problem_of(c):
        if c.get("q"):
            return c["q"]
        text = "\n".join(m.get("content") or "" for m in c.get("messages") or [])
        hit = [r["question_id"] for r in rows if r["question_content"].strip() in text]
        return hit[0] if len(hit) == 1 else None

    ok = [c for c in calls if "error" not in c]
    err = [c for c in calls if "error" in c]
    by_q = {}
    for c in ok:
        q = problem_of(c)
        if q is None:
            raise SystemExit(f"could not match a call to exactly one problem (start {c['start']})")
        by_q.setdefault(q, []).append(c)
    last = {q: cs[-1] for q, cs in by_q.items()}  # the answer that was kept
    tot = [sum(tokens(c.get("usage"))[i] for c in ok) for i in range(4)]  # every billed call, incl. superseded ones
    per = {}
    for r in rows:
        q = r["question_id"]
        c = last.get(q)
        rec = {"q": q, "difficulty": r["difficulty"], "platform": r["platform"], "passed": passed[q]}
        if c:
            _, _, out, reason = tokens(c.get("usage"))
            lat = c["end"] - c["start"]
            rec.update(latency=lat, out=out, reasoning=reason, finish=(c.get("finish") or [None])[0],
                       ttft=c["first_token"] - c["start"] if c.get("first_token") else None,
                       first_answer=c["first_content"] - c["start"] if c.get("first_content") else None,
                       speed=out / lat if lat > 0 and out else None,
                       decode=out / (c["end"] - c["first_token"]) if c.get("first_token") and out
                       and c["end"] > c["first_token"] else None)
        per[q] = rec
    have = [p for p in per.values() if "latency" in p]
    col = lambda k: [p[k] for p in have if p.get(k) is not None]  # noqa: E731
    n_pass = sum(passed.values())
    s = {"problems": len(rows), "passed": n_pass, "calls_ok": len(ok), "calls_error": len(err),
         "span_s": max(c["end"] for c in calls) - min(c["start"] for c in calls) if calls else 0,
         "active_s": covered([(c["start"], c["end"]) for c in ok]),
         "tokens": dict(zip(("input", "cache_hit", "output", "reasoning"), tot)),
         "latency": stats(col("latency")), "ttft": stats(col("ttft")), "first_answer": stats(col("first_answer")),
         "speed": stats(col("speed")), "decode": stats(col("decode")),
         "out_median": statistics.median(col("out")) if col("out") else None,
         "missing": [r["question_id"] for r in rows if r["question_id"] not in last],
         "errors": [c["error"][:200] for c in err[:20]], "per_problem": list(per.values())}
    if prices:
        cost = sum(call_cost(c, prices) for c in ok)
        s.update(prices=prices, cost=cost, cost_per_pass=cost / n_pass if n_pass else None)
    return s


def render(s, model, judged):
    def sec(v):
        return "—" if v is None else f"{v:.0f}" if v >= 10 else f"{v:.1f}"

    n, p, tk = s["problems"], s["passed"], s["tokens"]
    L = [f"# LiveCodeBench 延迟、token 和费用：{model}", "",
         f"- 题目：{n}，通过 {p}（pass@1 {100 * p / n:.1f}%，{judged}）",
         f"- 有效运行时间：{s['active_s'] / 60:.1f} 分钟（成功请求覆盖的时长）；首个请求发出到最后一个返回 {s['span_s'] / 60:.1f} 分钟",
         f"- API 调用：成功 {s['calls_ok']}，出错 {s['calls_error']}",
         f"- token：输入 {fmt_tok(tk['input'])}（其中缓存命中 {fmt_tok(tk['cache_hit'])}），输出 {fmt_tok(tk['output'])}"
         + (f"（其中思考 {fmt_tok(tk['reasoning'])}，占 {100 * tk['reasoning'] / tk['output']:.0f}%）" if tk["reasoning"] else "")]
    if s["missing"]:
        L.append(f"- 没有成功调用记录的题（请求都失败了、余额不足没发请求，或续跑时沿用了旧回答）：{', '.join(s['missing'])}")
    if "cost" in s:
        pr = s["prices"]
        L.append(f"- 费用：约 {s['cost']:.2f}；每道通过题 {s['cost_per_pass']:.3f}" if s["cost_per_pass"] is not None else
                 f"- 费用：约 {s['cost']:.2f}")
        unit = f"输入 {pr['in']} / 缓存命中 {pr['hit']} / 输出 {pr['out']}"
        if "off" in pr:
            o = pr["off"]
            hours = "、".join(f"{a:02d}:00–{b:02d}:00" for a, b in pr["peak_hours"])
            unit = f"高峰（UTC 周一至周五 {hours}）{unit}；其余时段 输入 {o['in']} / 缓存命中 {o['hit']} / 输出 {o['out']}"
        L.append(f"  （单价：{unit}，每百万 token；含被重试替换掉的调用）")
    rows = [("总延迟 ↓", s["latency"]), ("首个 token ↓", s["ttft"]), ("首个回答 token ↓", s["first_answer"])]
    if s["latency"]:
        L += ["", "## 每题时间（秒，并行跑时测得）", "", LEGEND, "",
              "| 指标 | 题数 | 平均 | 中位数 | P90 | 最长 |", "|---|---:|---:|---:|---:|---:|"]
        L += [f"| {name} | {v['n']} | {sec(v['mean'])} | {sec(v['median'])} | {sec(v['p90'])} | {sec(v['max'])} |"
              for name, v in rows if v]
        L.append("")
        L.append("首个 token 含排队和读题；首个回答 token 之前的时间主要是思考。这两项只有流式请求（默认）才有，题数可能少于总延迟。")
    sp, de = s["speed"], s["decode"]
    if sp or de:
        L += ["", "| 速度（token/秒）| 题数 | 中位数 | P90 |", "|---|---:|---:|---:|"]
        L += [f"| {name} | {v['n']} | {v['median']:.0f} | {v['p90']:.0f} |" for name, v in
              (("输出速度 ↑：输出 token ÷ 总延迟", sp), ("生成速度 ↑：输出 token ÷（总延迟 − 首个 token）", de)) if v]

    L += ["", "## 按难度", "", LEGEND, "",
          "| 难度 | 题数 | 通过 ↑ | 延迟中位数（秒）↓ | 首个 token 中位数（秒）↓ | 输出 token 平均 ↓ | 输出 token 最多 ↓ |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    per = s["per_problem"]
    for d in DIFFS:
        ps = [x for x in per if x["difficulty"] == d]
        if not ps:
            continue
        h = [x for x in ps if "latency" in x]
        tt = [x["ttft"] for x in h if x.get("ttft") is not None]
        L.append(f"| {d} | {len(ps)} | {sum(x['passed'] for x in ps)} | "
                 + (f"{sec(statistics.median(x['latency'] for x in h))} | {sec(statistics.median(tt)) if tt else '—'} | "
                    f"{fmt_tok(statistics.mean(x['out'] for x in h))} | {fmt_tok(max(x['out'] for x in h))} |"
                    if h else "— | — | — | — |"))

    L += ["", "## 每题", "", LEGEND, "",
          "| 题目 | 难度 | 通过 | 总延迟（秒）↓ | 首个 token（秒）↓ | 首个回答 token（秒）↓ | 输出 token ↓ | 其中思考 | 结束原因 |",
          "|---|---|:-:|---:|---:|---:|---:|---:|---|"]
    for x in sorted(per, key=lambda x: -x.get("latency", 0)):
        mark = "✓" if x["passed"] else "✗"
        if "latency" in x:
            L.append(f"| {x['q']} | {x['difficulty']} | {mark} | {sec(x['latency'])} | {sec(x['ttft'])} | "
                     f"{sec(x['first_answer'])} | {x['out']} | {x['reasoning'] or '—'} | {x['finish'] or '—'} |")
        else:
            L.append(f"| {x['q']} | {x['difficulty']} | {mark} | — | — | — | — | — | — |")
    if s["errors"]:
        L += ["", "## 出错的调用", ""] + [f"- {e}" for e in s["errors"]]
    return "\n".join(L) + "\n"


def env_float(k):
    v = os.environ.get(k)
    return float(v) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    ap.add_argument("--price-in", type=float, default=env_float("PRICE_IN"), help="input price per 1M tokens (cache miss)")
    ap.add_argument("--price-hit", type=float, default=env_float("PRICE_HIT"),
                    help="input price per 1M tokens (cache hit); default = --price-in")
    ap.add_argument("--price-out", type=float, default=env_float("PRICE_OUT"),
                    help="output price per 1M tokens (reasoning included)")
    for k in ("in", "hit", "out"):
        ap.add_argument(f"--price-off-{k}", type=float, default=env_float(f"PRICE_OFF_{k.upper()}"),
                        help=f"off-peak {k} price; then --price-{k} is the peak price")
    ap.add_argument("--peak-hours-utc", default=os.environ.get("PEAK_HOURS_UTC", "1-4,6-10"),
                    help="peak hours on weekdays (UTC), used only with off-peak prices; default DeepSeek's 1-4,6-10")
    a = ap.parse_args()
    prices = None
    if a.price_in is not None and a.price_out is not None:
        prices = {"in": a.price_in, "hit": a.price_in if a.price_hit is None else a.price_hit, "out": a.price_out}
        if a.price_off_in is not None and a.price_off_out is not None:
            prices["off"] = {"in": a.price_off_in, "out": a.price_off_out,
                             "hit": a.price_off_in if a.price_off_hit is None else a.price_off_hit}
            prices["peak_hours"] = [tuple(map(int, r.split("-"))) for r in a.peak_hours_utc.split(",") if r]
    f = glob.glob(os.path.join(a.run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if len(f) != 1:
        raise SystemExit(f"expected one *_eval_all.json under {a.run_dir}/output, found {len(f)}")
    rows = json.load(open(f[0]))
    calls = [json.loads(l) for l in open(os.path.join(a.run_dir, "usage.jsonl")) if l.strip()]
    rj = os.path.join(a.run_dir, "rejudge.jsonl")
    verdict = {v["q"]: v["passed"] for v in map(json.loads, open(rj))} if os.path.exists(rj) else {}
    passed = {r["question_id"]: verdict.get(r["question_id"], bool(r["graded_list"][0])) for r in rows}
    s = analyze(rows, calls, passed, prices)
    model = os.path.basename(os.path.dirname(f[0]))
    text = render(s, model, "按 cb rejudge 复核" if verdict else "LCB 自带判题")
    open(a.out or os.path.join(a.run_dir, "usage.md"), "w").write(text)
    json.dump({"model": model, "judged": "rejudge" if verdict else "lcb", **s},
              open(os.path.join(a.run_dir, "usage.json"), "w"), indent=1, ensure_ascii=False)
    print(text, end="")


if __name__ == "__main__":
    main()
