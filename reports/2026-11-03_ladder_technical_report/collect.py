"""Per-sample results of the four runs (ids and scores only, no problem content) -> paper_data.json.

  python collect.py <paper dir>

Reads data/dirs/<run>/{answers,judge,usage}.jsonl (one final answer per sample and the call that produced it),
data/dirs/meta.json (tier, source, subset per problem) and data/report_stats.json (per-tier aggregates of the
ladder report generator: runtime, complexity, static quality, cost). Every score is under the official time limit.
"""
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
DIRS = os.path.join(ROOT, "data", "dirs")
RUNS = {"kimi": "kimi-k3.1-pro", "kimi_high": "kimi-k3.1-pro-high", "deepseek": "deepseek-flash", "minimax": "MiniMax-M3.1-Flash"}
NAMES = {"kimi-k3.1-pro": "Kimi K3.1 Pro", "kimi-k3.1-pro-high": "Kimi K3.1 Pro（high）",
         "deepseek-flash": "DeepSeek Flash V4.1-1017", "MiniMax-M3.1-Flash": "MiniMax M3.1 Flash"}


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def failure(r, cont):
    """Main reason a sample is not solved under the official limit (same order as the ladder report)."""
    if r["strict_solved"]:
        return None
    if cont and r["strict_score"] > 0:
        return "partial"
    v = r.get("verdicts") or {}
    if "no code" in v:
        return "no code"
    if "timeout" in v:
        return "timeout"
    if "CE" in v:
        return "CE"
    if r.get("solved"):  # passes every test but not within the official limit
        return "TLE"
    for k in ("WA", "RE", "MLE", "TLE", "JE"):
        if v.get(k):
            return k
    return "partial"


meta = json.load(open(os.path.join(DIRS, "meta.json")))
problems = {p: {"tier": m["tier"], "source": m["source"], "subset": m["subset"], "title": m["title"], "lang": m["lang"],
                "continuous": (m.get("scoring") or {}).get("type") == "mean", "date": m.get("date")}
            for p, m in meta["meta"].items()}
samples = {}
for d, mid in RUNS.items():
    J = {}
    for r in jl(os.path.join(DIRS, d, "judge.jsonl")):
        J[r["q"]] = r
    U = {c["q"]: c for c in jl(os.path.join(DIRS, d, "usage.jsonl"))}
    rows = {}
    for a in jl(os.path.join(DIRS, d, "answers.jsonl")):
        q, pid = a["q"], a["pid"]
        if pid not in problems:
            continue
        r = J[q]
        c = U.get(q, {})
        out = (c.get("usage") or {}).get("completion_tokens") if isinstance(c.get("usage"), dict) else None
        ft = c.get("first_token")
        rows[q] = {"pid": pid, "tier": problems[pid]["tier"], "score": float(r["strict_score"]), "solved": bool(r["strict_solved"]),
                   "fail": failure(r, problems[pid]["continuous"]), "out": out,
                   "latency": (c["end"] - c["start"]) if c.get("end") else None,
                   "ttft": (ft - c["start"]) if ft else None,
                   "tps": (out / (c["end"] - ft)) if out and ft and c["end"] > ft and "timeout" not in (c.get("finish") or []) else None}
    samples[mid] = rows
stats = {s["model_id"]: s for s in json.load(open(os.path.join(ROOT, "data", "report_stats.json")))}
agg = {}
for mid, s in stats.items():
    agg[mid] = {"tiers": {t: {k: v.get(k) for k in ("perf_n", "perf_geo", "perf_faster", "perf_2x", "mem_geo", "fails")}
                          for t, v in s["tiers"].items()},
                "subsets": {k: {"problems": v["problems"], "samples": v["samples"], "pass1": v["pass1"], "score": v["score"]}
                            for k, v in s["subsets"].items()},
                "complexity": s["complexity"], "quality": s["quality"],
                "usage": {"per_tier": s["usage"]["per_tier"], "cost": s["usage"]["cost"], "calls": s["usage"]["calls"],
                          "completion": s["usage"]["completion"], "reasoning": s["usage"]["reasoning"],
                          "tps_median": s["usage"].get("tps_median"), "ttft": s["usage"]["ttft"], "latency": s["usage"]["latency"]}}
json.dump({"problems": problems, "tiers": meta["tiers"], "names": NAMES, "samples": samples, "agg": agg},
          open(os.path.join(ROOT, "paper_data.json"), "w"), ensure_ascii=False, indent=0)
print({m: len(v) for m, v in samples.items()}, len(problems))
