"""Statistics of the codingBench ladder technical report, from paper_data.json -> analysis.json.

  python analysis.py <paper dir>

Unit of resampling = the problem (each problem's samples stay together). B = 2000, seed 0. Pooled L1-L4 pass@1 is
over samples; its bootstrap resamples problems within each tier. Pairwise differences use the same resampled
problems for both models (paired). Per-problem comparison: mean score over the problem's samples, a gap under
0.05 points is a tie, exact two-sided sign test on wins and losses.
"""
import json
import math
import os
import random
import statistics as st
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(ROOT, "paper_data.json")))
TIERS = ["L1", "L2", "L3", "L4", "L5"]
DISC = ["L1", "L2", "L3", "L4"]
MAIN = ["kimi-k3.1-pro", "deepseek-flash", "MiniMax-M3.1-Flash"]
HIGH = "kimi-k3.1-pro-high"
B = 2000
P = D["problems"]
S = D["samples"]


def by_problem(m, tiers):
    out = {}
    for q, r in S[m].items():
        if r["tier"] in tiers:
            out.setdefault(r["pid"], []).append(r)
    return out


def tier_pids(t):
    return sorted(p for p, v in P.items() if v["tier"] == t)


def stat(groups, pids, key):
    xs = [x for p in pids for x in groups[p]]
    return 100 * st.mean(float(x[key]) for x in xs) if key == "solved" else st.mean(x["score"] for x in xs)


def sign_p(w, l):
    n = w + l
    if n == 0:
        return None
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


rng = random.Random(0)
boot = {t: [[rng.choice(tier_pids(t)) for _ in tier_pids(t)] for _ in range(B)] for t in TIERS}


def ci(vals):
    v = sorted(vals)
    return [v[int(0.025 * B)], v[int(0.975 * B) - 1]]


def metrics(m, tiers=TIERS):
    g = by_problem(m, tiers)
    res = {}
    for t in tiers:
        pids = tier_pids(t)
        if not all(p in g for p in pids):
            continue
        d = {"n_problems": len(pids), "n_samples": sum(len(g[p]) for p in pids),
             "score": stat(g, pids, "score"), "score_ci": ci([stat(g, bs, "score") for bs in boot[t]])}
        if t != "L5":
            d["pass1"] = stat(g, pids, "solved")
            d["pass1_ci"] = ci([stat(g, bs, "solved") for bs in boot[t]])
            d["passn"] = 100 * st.mean(any(x["solved"] for x in g[p]) for p in pids)
        res[t] = d
    if all(t in res for t in DISC):
        pool = [p for t in DISC for p in tier_pids(t)]
        res["L1-L4"] = {"pass1": stat(g, pool, "solved"), "score": stat(g, pool, "score"),
                        "pass1_ci": ci([stat(g, [p for t in DISC for p in boot[t][i]], "solved") for i in range(B)]),
                        "n_samples": sum(len(g[p]) for p in pool)}
    return res


def pair(a, b, tiers=TIERS):
    ga, gb = by_problem(a, tiers), by_problem(b, tiers)
    out = {}
    for t in tiers:
        pids = tier_pids(t)
        key = "score" if t == "L5" else "solved"
        d = stat(ga, pids, key) - stat(gb, pids, key)
        diffs = [stat(ga, bs, key) - stat(gb, bs, key) for bs in boot[t]]
        w = sum(st.mean(x["score"] for x in ga[p]) - st.mean(x["score"] for x in gb[p]) >= 0.05 for p in pids)
        l = sum(st.mean(x["score"] for x in gb[p]) - st.mean(x["score"] for x in ga[p]) >= 0.05 for p in pids)
        out[t] = {"metric": "score" if t == "L5" else "pass1", "diff": d, "ci": ci(diffs), "wins": w, "losses": l,
                  "ties": len(pids) - w - l, "p": sign_p(w, l)}
    if all(t in tiers for t in DISC):
        pool = [p for t in DISC for p in tier_pids(t)]
        diffs = []
        for i in range(B):
            bs = [p for t in DISC for p in boot[t][i]]
            diffs.append(stat(ga, bs, "solved") - stat(gb, bs, "solved"))
        allp = [p for t in TIERS for p in tier_pids(t)]
        w = sum(st.mean(x["score"] for x in ga[p]) - st.mean(x["score"] for x in gb[p]) >= 0.05 for p in allp)
        l = sum(st.mean(x["score"] for x in gb[p]) - st.mean(x["score"] for x in ga[p]) >= 0.05 for p in allp)
        out["L1-L4"] = {"metric": "pass1", "diff": stat(ga, pool, "solved") - stat(gb, pool, "solved"), "ci": ci(diffs)}
        out["all"] = {"wins": w, "losses": l, "ties": len(allp) - w - l, "p": sign_p(w, l)}
    return out


A = {"names": D["names"], "tier_n": {t: len(tier_pids(t)) for t in TIERS}, "metrics": {}, "pairs": {}}
for m in MAIN:
    A["metrics"][m] = metrics(m)
A["metrics"][HIGH] = metrics(HIGH, ["L4", "L5"])
for a, b in [("kimi-k3.1-pro", "deepseek-flash"), ("kimi-k3.1-pro", "MiniMax-M3.1-Flash"), ("deepseek-flash", "MiniMax-M3.1-Flash")]:
    A["pairs"][f"{a}|{b}"] = pair(a, b)
A["pairs"][f"kimi-k3.1-pro|{HIGH}"] = pair("kimi-k3.1-pro", HIGH, ["L4", "L5"])
# effort: the samples whose max answer differs from the high answer (all L5; the L4 samples high did not solve)
eff = {}
for t in ("L4", "L5"):
    qs = sorted(q for q, r in S[HIGH].items() if r["tier"] == t)
    # L4: the samples high did not solve (a high answer that passes every test but only past the official limit was kept)
    changed = qs if t == "L5" else [q for q in qs if not S[HIGH][q]["solved"] and S[HIGH][q]["fail"] != "TLE"]
    hi = [S[HIGH][q]["score"] for q in changed]
    mx = [S["kimi-k3.1-pro"][q]["score"] for q in changed]
    r2 = random.Random(1)
    diffs = []
    for _ in range(B):
        idx = [r2.randrange(len(changed)) for _ in changed]
        diffs.append(st.mean(mx[i] - hi[i] for i in idx))
    up = sum(b - a >= 0.05 for a, b in zip(hi, mx))
    dn = sum(a - b >= 0.05 for a, b in zip(hi, mx))
    eff[t] = {"n": len(changed), "high_solved": sum(S[HIGH][q]["solved"] for q in changed),
              "max_solved": sum(S["kimi-k3.1-pro"][q]["solved"] for q in changed), "high_mean": st.mean(hi), "max_mean": st.mean(mx),
              "diff": st.mean(mx) - st.mean(hi), "ci": ci(diffs), "up": up, "down": dn, "p": sign_p(up, dn),
              "samples": [[q, S[HIGH][q]["score"], S["kimi-k3.1-pro"][q]["score"]] for q in changed]}
    for m, key in ((HIGH, "high"), ("kimi-k3.1-pro", "max")):  # output, speed and latency on the same samples
        rs = [S[m][q] for q in changed]
        eff[t][f"{key}_out"] = st.mean(r["out"] for r in rs if r["out"])
        eff[t][f"{key}_tps"] = st.median(r["tps"] for r in rs if r["tps"])
        eff[t][f"{key}_lat"] = st.median(r["latency"] for r in rs if r["latency"])
eff["L5"]["ci"] = A["pairs"][f"kimi-k3.1-pro|{HIGH}"]["L5"]["ci"]  # one sample per problem: the same problem bootstrap as the pairs
A["effort"] = eff
# usage per model: per tier and total from the samples (one call per sample)
A["usage"] = {}
for m in MAIN + [HIGH]:
    u = {}
    rows = list(S[m].values())
    for t in TIERS + ["all"]:
        xs = [r for r in rows if t == "all" or r["tier"] == t]
        if not xs:
            continue
        outs = [r["out"] for r in xs if r["out"]]
        tps = [r["tps"] for r in xs if r["tps"]]
        u[t] = {"calls": len(xs), "out_sum": sum(outs), "out_mean": st.mean(outs) if outs else None,
                "tps_median": st.median(tps) if tps else None,
                "ttft_median": st.median([r["ttft"] for r in xs if r["ttft"]]) if any(r["ttft"] for r in xs) else None,
                "lat_median": st.median([r["latency"] for r in xs if r["latency"]])}
        pt = D["agg"][m]["usage"]["per_tier"]
        u[t]["cost"] = D["agg"][m]["usage"]["cost"] if t == "all" else (pt.get(t) or {}).get("cost")
        solved = sum(r["solved"] for r in xs if r["tier"] != "L5")
        if t != "L5":
            c = u[t]["cost"] if t != "all" else sum((pt.get(x) or {}).get("cost", 0) for x in DISC)
            u[t]["cost_per_solved"] = c / solved if solved else None
    A["usage"][m] = u
json.dump(A, open(os.path.join(ROOT, "analysis.json"), "w"), ensure_ascii=False, indent=1)
for m in MAIN + [HIGH]:
    print(m, {t: (round(v.get("pass1", v["score"]), 1), [round(x, 1) for x in (v.get("pass1_ci") or v.get("score_ci"))]) for t, v in A["metrics"][m].items()})
for k, v in A["pairs"].items():
    print(k, {t: (round(x["diff"], 1), [round(y, 1) for y in x["ci"]], x.get("wins"), x.get("losses"), None if x.get("p") is None else round(x["p"], 4)) for t, x in v.items() if "diff" in x}, v.get("all"))
print("effort", {t: {k: (round(x, 2) if isinstance(x, float) else x) for k, x in v.items() if k != "samples"} for t, v in eff.items()})
print("usage", {m: {t: (u["calls"], round(u["out_mean"] or 0), round(u["tps_median"] or 0, 1), round(u["cost"] or 0, 2), round(u.get("cost_per_solved") or 0, 3)) for t, u in v.items()} for m, v in A["usage"].items()})
