"""Every number of the ladder technical report from the committed run report (report.json of the DeepSeek / MiniMax
comparison): per-tier pass@1 and mean score with bootstrap intervals over problems, paired differences, per-problem
wins / ties / losses with the exact sign test, the 2026 subset, and the per-tier efficiency, complexity, failure,
static-quality and usage tables carried over; written to analysis.json.

  python paper/analysis.py
"""
import json
import math
import os
import random
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "..", "reports", "2026-10-29_ladder_deepseek-flash_vs_minimax-m3.1-flash", "report.json")
R = {m["model_id"]: m for m in json.load(open(RUN))}
MODELS = ["deepseek-flash", "MiniMax-M3.1-Flash"]
TIERS = ["L1", "L2", "L3", "L4", "L5"]
CLOSED = TIERS[:4]  # pass / fail tiers; L5 is a continuous score
B = 2000
rng = random.Random(0)

pp = {m: R[m]["per_problem"] for m in MODELS}
ids = sorted(set(pp[MODELS[0]]) & set(pp[MODELS[1]]))
by_tier = {t: [i for i in ids if pp[MODELS[0]][i]["tier"] == t] for t in TIERS}


def pass1(m, pick):
    """solved samples / samples over the picked problems (as the run report: samples, not problems, are counted)"""
    n = sum(pp[m][i]["n"] for i in pick)
    return 100 * sum(pp[m][i]["solved"] for i in pick) / n if n else None


def score(m, pick):
    return statistics.mean(pp[m][i]["score"] for i in pick)


def stats(pick):
    out = {}
    for m in MODELS:
        out[m] = {t: {"pass1": pass1(m, pick[t]) if t in CLOSED else None, "score": score(m, pick[t])} for t in TIERS}
        out[m]["L1-L4"] = {"pass1": pass1(m, [i for t in CLOSED for i in pick[t]]),
                           "score": score(m, [i for t in CLOSED for i in pick[t]])}
    return out


point = stats(by_tier)
boots = [stats({t: [rng.choice(v) for _ in v] for t, v in by_tier.items()}) for _ in range(B)]


def ci(xs):
    xs = sorted(xs)
    return [xs[int(0.025 * (len(xs) - 1))], xs[int(0.975 * (len(xs) - 1))]]


GROUPS = TIERS + ["L1-L4"]
out = {"models": MODELS, "names": {m: R[m]["model"] for m in MODELS}, "tiers": TIERS, "n_problems": len(ids),
       "tier_n": {t: len(v) for t, v in by_tier.items()}, "point": point}
out["ci"] = {m: {g: {k: ci([b[m][g][k] for b in boots]) for k in ("pass1", "score") if point[m][g][k] is not None}
                 for g in GROUPS} for m in MODELS}
a, b = MODELS
out["diff"] = {g: {k: {"diff": point[b][g][k] - point[a][g][k], "ci": ci([x[b][g][k] - x[a][g][k] for x in boots])}
                   for k in ("pass1", "score") if point[a][g][k] is not None} for g in GROUPS}


def sign_p(w, l_):
    """two-sided exact sign test"""
    n = w + l_
    if n == 0:
        return None
    k = min(w, l_)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


wtl = {}
for g in GROUPS:
    pick = [i for t in (CLOSED if g == "L1-L4" else [g]) for i in by_tier[t]]
    d = [pp[b][i]["score"] - pp[a][i]["score"] for i in pick]
    w, l_ = sum(x >= 0.05 for x in d), sum(x <= -0.05 for x in d)  # wins of b (MiniMax) / of a (DeepSeek)
    wtl[g] = {"minimax_better": w, "tie": len(d) - w - l_, "deepseek_better": l_, "p": sign_p(w, l_)}
d = [pp[b][i]["score"] - pp[a][i]["score"] for i in ids]
w, l_ = sum(x >= 0.05 for x in d), sum(x <= -0.05 for x in d)
wtl["all"] = {"minimax_better": w, "tie": len(d) - w - l_, "deepseek_better": l_, "p": sign_p(w, l_)}
out["wtl"] = wtl
# carried over from the run report, per model and tier
keep = ("problems", "samples", "pass1", "pass1_strict", "score", "score_strict", "passn", "n_per_problem", "fails",
        "perf_n", "perf_geo", "perf_faster", "perf_2x", "mem_geo")
out["tier"] = {m: {t: {k: R[m]["tiers"][t][k] for k in keep} for t in TIERS} for m in MODELS}
out["subsets"] = {m: R[m]["subsets"] for m in MODELS}
out["complexity"] = {m: R[m]["complexity"] for m in MODELS}
out["quality"] = {m: R[m]["quality"] for m in MODELS}
out["usage"] = {m: R[m]["usage"] for m in MODELS}
out["dropped"] = {m: R[m]["dropped"] for m in MODELS}
out["timeouts"] = {m: len(R[m]["timeouts"]) for m in MODELS}
# solved at least once by neither / one / both (L1-L4) and cost per solved sample
solved_by = {}
for t in CLOSED:
    k = [sum(pp[m][i]["solved"] > 0 for m in MODELS) for i in by_tier[t]]
    solved_by[t] = [k.count(0), k.count(1), k.count(2)]
out["solved_by"] = solved_by
comp = {}
for i in ids:
    x = pp[MODELS[0]][i]
    comp.setdefault(x["tier"], {}).setdefault(x["subset"], 0)
    comp[x["tier"]][x["subset"]] += 1
out["composition"] = comp
out["cost_per_solved"] = {m: sum(R[m]["usage"]["per_tier"][t]["cost"] for t in CLOSED) /
                          sum(pp[m][i]["solved"] for t in CLOSED for i in by_tier[t]) for m in MODELS}
out["out_per_call"] = {m: R[m]["usage"]["completion"] / R[m]["usage"]["calls"] for m in MODELS}
# generation speed after the first token, token-weighted over the run (cut-off calls carry estimated tokens)
out["gen_speed"] = {m: R[m]["usage"]["completion"] / ((R[m]["usage"]["latency"]["mean"] - R[m]["usage"]["ttft"]["mean"]) *
                                                      R[m]["usage"]["calls"]) for m in MODELS}
out["reasoning_share"] = {m: 100 * R[m]["usage"]["reasoning"] / R[m]["usage"]["completion"] for m in MODELS}
json.dump(out, open(os.path.join(HERE, "analysis.json"), "w"), indent=1, ensure_ascii=False)

for m in MODELS:
    print(f"{out['names'][m]:<26}", " | ".join(
        f"{g} p@1 {point[m][g]['pass1']:.1f}" if point[m][g]["pass1"] is not None else f"{g} score {point[m][g]['score']:.1f}"
        for g in GROUPS), f"| ${R[m]['usage']['cost']:.2f} ${out['cost_per_solved'][m]:.3f}/solved")
for g in GROUPS:
    print(g, {k: (round(v["diff"], 1), [round(x, 1) for x in v["ci"]]) for k, v in out["diff"][g].items()}, wtl[g])
print("solved by 0/1/2:", solved_by, "all", wtl["all"])
