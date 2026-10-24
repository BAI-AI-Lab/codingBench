"""Build perf.tex (performance and static-metric tables) from perf.jsonl, static.jsonl and sizes.jsonl."""
import collections
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = [("kimi-k3.1-pro", "Kimi"), ("deepseek-flash", "DS-Flash"), ("deepseek-v4-pro", "DS-Pro")]
THRESH = 0.1  # s of CPU above the startup baseline for the slowest answer before a problem counts as measurable
rows = [json.loads(l) for l in open(os.path.join(HERE, "perf.jsonl"))]
static = [json.loads(l) for l in open(os.path.join(HERE, "static.jsonl"))]
sizes = {r["q"]: r for r in map(json.loads, open(os.path.join(HERE, "sizes.jsonl")))}
probs = {p["question_id"]: p for p in json.load(open(os.path.join(HERE, "problems35.json")))}

base = [r["cpu"] for r in rows if r["model"] == "baseline"]
base_rss = statistics.median(r["rss_kb"] for r in rows if r["model"] == "baseline")
B = statistics.median(base)
assert all(r.get("ok") for r in rows), "every measured run must be correct"

# per (model, q, test): median over reps of net CPU (AtCoder: process CPU - baseline; LeetCode: call CPU) and RSS
per = collections.defaultdict(list)
for r in rows:
    if r["model"] == "baseline":
        continue
    net = r["call_cpu"] if "call_cpu" in r else max(0.0, r["cpu"] - B)
    per[(r["model"], r["q"], r["test"])].append((net, r["rss_kb"], r["cpu"]))
spread = []
med = {}
for k, v in per.items():
    nets = [x[0] for x in v]
    m = statistics.median(nets)
    med[k] = (m, statistics.median(x[1] for x in v))
    if m >= 0.1 and len(nets) >= 3:
        spread.append((max(nets) - min(nets)) / m)

prob = collections.defaultdict(dict)  # q -> model -> (max-test net cpu, total net cpu, peak rss KB)
for (m, q, t), (c, rss) in med.items():
    a = prob[q].setdefault(m, [0.0, 0.0, 0])
    a[0], a[1], a[2] = max(a[0], c), a[1] + c, max(a[2], rss)
measurable = sorted((q for q, d in prob.items() if max(v[0] for v in d.values()) >= THRESH),
                    key=lambda q: (probs[q]["difficulty"] != "medium", q))
common = [q for q in measurable if all(m in prob[q] for m, _ in MODELS)]

L = []


def mac(name, val):
    L.append(f"\\newcommand{{\\{name}}}{{{val}}}")


def esc(q):
    return q.replace("_", "\\_")


mac("PerfBaseline", f"{1000 * B:.1f}")
mac("PerfBaselineRange", f"{1000 * min(base):.1f}--{1000 * max(base):.1f}")
mac("PerfBaseRss", f"{base_rss / 1024:.1f}")
mac("PerfNoiseMedian", f"{100 * statistics.median(spread):.1f}")
mac("PerfNoiseHigh", f"{100 * sorted(spread)[int(0.9 * (len(spread) - 1))]:.1f}")
mac("PerfRuns", f"{sum(1 for r in rows if r['model'] != 'baseline'):,}".replace(",", "{,}"))
mac("PerfMeasurable", len(measurable))
mac("PerfCommon", len(common))
mac("PerfThresh", f"{THRESH:.1f}")
small = sorted(q for q in prob if q not in measurable)
mac("PerfSmallList", "、".join(f"\\texttt{{{esc(q)}}}" for q in small))
mac("PerfSmallN", len(small))

# per-problem table
L.append("\\newcommand{\\PerfRows}{%")
for q in measurable:
    d = prob[q]
    cpus = {m: d[m][0] for m, _ in MODELS if m in d}
    best = min(cpus.values())
    cells = []
    for m, _ in MODELS:
        if m not in d:
            cells.append("— & —")
            continue
        c = d[m][0]
        txt = f"{c:.2f}"
        if c == best:
            txt = f"\\textbf{{{txt}}}"
        elif best > 0 and c / best >= 2:
            txt += f"\\,({c / best:.1f}$\\times$)"
        cells.append(f"{txt} & {d[m][2] / 1024:.0f}")
    kind = "LC" if probs[q]["platform"] == "leetcode" else "AC"
    L.append(f"\\texttt{{{esc(q)}}} & {'中' if probs[q]['difficulty'] == 'medium' else '难'} & {kind} & "
             f"{sizes[q]['max_bytes'] / 1024:.0f} & " + " & ".join(cells) + " \\\\")
L.append("}")

# per-model aggregates over problems measurable and passed by all three
L.append("\\newcommand{\\PerfSummaryRows}{%")
agg = {}
for m, short in MODELS:
    ratios = [prob[q][m][0] / max(1e-3, min(prob[q][x][0] for x, _ in MODELS)) for q in common]
    wins = sum(prob[q][m][0] == min(prob[q][x][0] for x, _ in MODELS) for q in common)
    slow2 = sum(r >= 2 for r in ratios)
    tot = sum(prob[q][m][1] for q in common)
    rss = statistics.median(prob[q][m][2] for q in common) / 1024
    rss_max = max(prob[q][m][2] for q in common) / 1024
    agg[m] = (math.exp(statistics.mean(map(math.log, ratios))), wins, slow2, tot, rss, rss_max)
gm_best = min(a[0] for a in agg.values())
for m, short in MODELS:
    g, wins, slow2, tot, rss, rss_max = agg[m]
    gtxt = f"\\textbf{{{g:.2f}}}" if g == gm_best else f"{g:.2f}"
    L.append(f"{short} & {gtxt} & {wins} & {slow2} & {tot:.1f} & {rss:.0f} & {rss_max:.0f} \\\\")
L.append("}")
for m, short in MODELS:
    tag = short.replace("-", "")
    mac(f"{tag}GM", f"{agg[m][0]:.2f}")
    mac(f"{tag}Wins", agg[m][1])
    mac(f"{tag}SlowTwo", agg[m][2])

# static metrics over problems all three passed
st_common = set.intersection(*[{r["q"] for r in static if r["model"] == m} for m, _ in MODELS])
mac("StaticCommon", len(st_common))
io_rows = []
L.append("\\newcommand{\\StaticRows}{%")
for m, short in MODELS:
    R = [r for r in static if r["model"] == m and r["q"] in st_common]
    io = collections.Counter(r["io"] for r in R if r["platform"] == "atcoder")
    io_txt = "、".join(f"{k} {v}" for k, v in io.most_common())
    L.append(f"{short} & {sum(r['sloc'] for r in R)} & {statistics.median(r['sloc'] for r in R):.0f} & "
             f"{sum(r['comments'] for r in R)} & {statistics.median(r['cc_total'] for r in R):.0f} & "
             f"{statistics.median(r['mi'] for r in R):.1f} & {statistics.median(r['depth'] for r in R):.0f} & "
             f"{sum(r['pyflakes'] for r in R)} \\\\")
    io_rows.append(f"{short} & {io_txt} \\\\")
L.append("}")
L += ["\\newcommand{\\StaticIoRows}{%"] + io_rows + ["}"]
open(os.path.join(HERE, "perf.tex"), "w").write("\n".join(L) + "\n")
print("baseline %.1f ms; measurable %d (common %d); noise median %.1f%%" % (1000 * B, len(measurable), len(common),
                                                                        100 * statistics.median(spread)))
for m, short in MODELS:
    print(short, "geo-mean ratio %.2f wins %d >=2x %d total %.1fs rss med %.0fMB" % (agg[m][:5]))
