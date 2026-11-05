"""LaTeX tables of the codingBench ladder technical report, from analysis.json and paper_data.json.

  python make_tables.py <paper dir>      -> <paper dir>/tables/*.tex
"""
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(ROOT, "analysis.json")))
D = json.load(open(os.path.join(ROOT, "paper_data.json")))
OUT = os.path.join(ROOT, "tables")
os.makedirs(OUT, exist_ok=True)
TIERS = ["L1", "L2", "L3", "L4", "L5"]
TN = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式", "L1-L4": "L1--L4 合计"}
KIMI, HIGH, DS, MM = "kimi-k3.1-pro", "kimi-k3.1-pro-high", "deepseek-flash", "MiniMax-M3.1-Flash"
MAIN = [KIMI, DS, MM]
SHORT = {KIMI: "Kimi", HIGH: "Kimi（high）", DS: "DeepSeek", MM: "MiniMax"}
AGG = D["agg"]
U = A["usage"]


def f(x, nd=1):
    return "--" if x is None else f"{x:.{nd}f}"


def ci(c, nd=1):
    return f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]"


def sgn(x, nd=1):
    return f"{x:+.{nd}f}".replace("-", "$-$")


def models_in(t):
    return [KIMI] + ([HIGH] if t in ("L4", "L5") else []) + [DS, MM]


def write(name, body):
    open(os.path.join(OUT, name), "w").write(body)


def block(rows_by_tier, ncols):
    """rows grouped by tier with \\multirow on the tier cell and a rule between tiers."""
    out = []
    for k, (t, rows) in enumerate(rows_by_tier):
        for i, r in enumerate(rows):
            cell = f"\\multirow{{{len(rows)}}}{{*}}{{{TN[t]}}}" if i == 0 else ""
            out.append(" & ".join([cell] + r) + " \\\\")
        if k < len(rows_by_tier) - 1:
            out.append(f"\\cmidrule(lr){{1-{ncols}}}")
    return "\n".join(out)


# main results ------------------------------------------------------------------------------------------------------
rows = []
for t in TIERS + ["L1-L4"]:
    ms = models_in(t) if t != "L1-L4" else MAIN
    vals = {m: A["metrics"][m][t] for m in ms if t in A["metrics"][m]}
    best_p = max((v.get("pass1", -1) for v in vals.values()), default=None)
    best_s = max((v["score"] for v in vals.values()), default=None)
    rr = []
    for m, v in vals.items():
        p = "--" if "pass1" not in v else (("\\textbf{%s}" if abs(v["pass1"] - best_p) < 1e-9 else "%s") % f(v["pass1"])) + f" {ci(v['pass1_ci'])}"
        s = (("\\textbf{%s}" if abs(v["score"] - best_s) < 1e-9 else "%s") % f(v["score"])) + (f" {ci(v['score_ci'])}" if "score_ci" in v else "")
        pn = f(v["passn"]) if "passn" in v and t in ("L3", "L4") else "--"
        nsamp = str(v.get("n_samples", ""))
        rr.append([SHORT[m], nsamp, p, s, pn])
    rows.append((t, rr))
write("main_results.tex", "\\begin{tabular}{@{}llrrrr@{}}\n\\toprule\n档位 & 模型 & 采样数 & pass@1（\\%）$\\uparrow$ [95\\% 区间] & 平均得分 $\\uparrow$ [95\\% 区间] & pass@3（\\%）$\\uparrow$ \\\\\n\\midrule\n"
      + block(rows, 6) + "\n\\bottomrule\n\\end{tabular}\n")

# pairwise ------------------------------------------------------------------------------------------------------------
pairs = [(KIMI, DS), (KIMI, MM), (DS, MM)]
head = " & ".join(f"\\multicolumn{{2}}{{c}}{{{SHORT[a]} $-$ {SHORT[b]}}}" for a, b in pairs)
lines = []
for t in ["L1", "L2", "L3", "L4", "L1-L4", "L5"]:
    cells = [TN[t]]
    for a, b in pairs:
        p = A["pairs"][f"{a}|{b}"][t]
        sig = p["ci"][0] > 0 or p["ci"][1] < 0
        d = sgn(p["diff"]) + ("$^{*}$" if sig else "")
        cells += [f"{d} {ci(p['ci'])}".replace("-", "$-$").replace("$$-$$", "$-$"), f"{p['wins']}/{p['ties']}/{p['losses']}" if "wins" in p else "--"]
    lines.append(" & ".join(cells) + " \\\\")
    if t in ("L4", "L1-L4"):
        lines.append("\\midrule")
allr = ["全部 112 题（逐题符号检验）"]
for a, b in pairs:
    x = A["pairs"][f"{a}|{b}"]["all"]
    pv = "$p<0.001$" if x["p"] < 0.001 else f"$p={x['p']:.3f}$"
    allr += ["", f"{x['wins']}/{x['ties']}/{x['losses']}，{pv}"]
lines.append("\\midrule\n" + " & ".join(allr) + " \\\\")
write("pairwise.tex", "\\begin{tabular}{@{}lrrrrrr@{}}\n\\toprule\n & " + head + " \\\\\n\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}\n档位 & 差值 [95\\% 区间] & 胜/平/负 & 差值 [95\\% 区间] & 胜/平/负 & 差值 [95\\% 区间] & 胜/平/负 \\\\\n\\midrule\n"
      + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")

# effort ----------------------------------------------------------------------------------------------------------------
e = A["effort"]
lines = []
for t, lab in (("L4", "L4（high 未解出的采样）"), ("L5", "L5（全部采样）")):
    x = e[t]
    pv = "$p<0.001$" if x["p"] < 0.001 else f"$p={x['p']:.2f}$"
    sol = f"{x['high_solved']} $\\rightarrow$ {x['max_solved']}" if t == "L4" else "--"
    lines.append(f"{lab} & {x['n']} & {sol} & {x['high_mean']:.1f} $\\rightarrow$ {x['max_mean']:.1f} & {sgn(x['diff'])} {ci(x['ci'])} & {x['up']}/{x['n'] - x['up'] - x['down']}/{x['down']}，{pv} \\\\".replace("[-", "[$-$"))
write("effort.tex", "\\begin{tabular}{@{}lrrrrr@{}}\n\\toprule\n比较范围 & 采样数 & 解出 high $\\rightarrow$ max & 平均得分 high $\\rightarrow$ max & 差值 [95\\% 区间] & 提高/持平/降低 \\\\\n\\midrule\n"
      + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")
lines = []
for t in ("L4", "L5"):
    x = e[t]
    rr = [[k, f"{x[k + '_out'] / 1000:.1f}k", f(x[k + "_tps"]), f"{x[k + '_lat'] / 60:.1f}"] for k in ("high", "max")]
    lines.append((t, rr))
write("effort_cost.tex", "\\begin{tabular}{@{}llrrr@{}}\n\\toprule\n档位 & 思考强度 & 每次输出 token $\\downarrow$ & 输出速度（tokens/s）$\\uparrow$ & 延迟中位数（分钟）$\\downarrow$ \\\\\n\\midrule\n"
      + block(lines, 5) + "\n\\bottomrule\n\\end{tabular}\n")

# subsets (contamination check) -----------------------------------------------------------------------------------------
SUB = {"2026": "EGOI 2026", "USACO 2024-25": "USACO 2024--25", "USACO 2025-26": "USACO 2025--26"}
lines = []
for t in ("L3", "L4"):
    rr = []
    for sub in ("2026", "USACO 2024-25", "USACO 2025-26"):
        k = f"{t}|{sub}"
        ms = models_in(t)
        if k not in AGG[KIMI]["subsets"]:
            continue
        n = AGG[KIMI]["subsets"][k]
        cells = [SUB[sub], f"{n['problems']}"]
        for m in [KIMI, HIGH, DS, MM]:
            s = AGG[m]["subsets"].get(k)
            cells.append(f(s["pass1"]) if s and m in ms else "--")
        rr.append(cells)
    lines.append((t, rr))
write("subsets.tex", "\\begin{tabular}{@{}llrrrrr@{}}\n\\toprule\n档位 & 子集 & 题数 & Kimi & Kimi（high） & DeepSeek & MiniMax \\\\\n\\midrule\n" + block(lines, 7) + "\n\\bottomrule\n\\end{tabular}\n")

# runtime and memory ----------------------------------------------------------------------------------------------------
lines = []
for t in ("L1", "L2", "L3", "L4"):
    rr = []
    for m in models_in(t):
        v = AGG[m]["tiers"][t]
        rr.append([SHORT[m], str(v["perf_n"]), f"{v['perf_geo']:.2f}$\\times$", str(v["perf_faster"]), str(v["perf_2x"]), f"{v['mem_geo']:.2f}$\\times$"])
    lines.append((t, rr))
write("perf.tex", "\\begin{tabular}{@{}llrrrrr@{}}\n\\toprule\n档位 & 模型 & 比较的答案数 & CPU 时间倍数 $\\downarrow$ & 快于官方解 & 慢 2 倍以上 & 峰值内存倍数 $\\downarrow$ \\\\\n\\midrule\n"
      + block(lines, 7) + "\n\\bottomrule\n\\end{tabular}\n")

# complexity (time) -----------------------------------------------------------------------------------------------------
CPLX = [("better", "更优"), ("same", "同阶"), ("worse", "更差"), ("uncertain", "不确定"), ("not measurable", "不可测")]
lines = []
for t in ("L1", "L2", "L3", "L4"):
    rr = []
    for m in models_in(t):
        c = (AGG[m]["complexity"].get(t) or {}).get("time")
        if not c:
            continue
        rr.append([SHORT[m]] + [str(c["classes"].get(k, 0)) for k, _ in CPLX] + [f(c["k_median"], 2)])
    lines.append((t, rr))
write("complexity.tex", "\\begin{tabular}{@{}llrrrrrr@{}}\n\\toprule\n档位 & 模型 & " + " & ".join(n for _, n in CPLX) + " & $k$ 中位数 \\\\\n\\midrule\n"
      + block(lines, 8) + "\n\\bottomrule\n\\end{tabular}\n")

# failures --------------------------------------------------------------------------------------------------------------
FAIL = [("no code", "无代码"), ("timeout", "生成超时"), ("CE", "编译错误"), ("WA", "答案错误"), ("RE", "运行错误"), ("TLE", "超时"), ("partial", "部分分")]
lines = []
for t in TIERS:
    rr = []
    for m in models_in(t):
        fl = AGG[m]["tiers"][t]["fails"]
        n = sum(1 for r in D["samples"][m].values() if r["tier"] == t)
        rr.append([SHORT[m], str(n), str(sum(fl.values()))] + [str(fl.get(k, 0)) for k, _ in FAIL])
    lines.append((t, rr))
write("failures.tex", "\\begin{tabular}{@{}llrrrrrrrrr@{}}\n\\toprule\n档位 & 模型 & 答案数 & 未解出 & " + " & ".join(n for _, n in FAIL) + " \\\\\n\\midrule\n"
      + block(lines, 10) + "\n\\bottomrule\n\\end{tabular}\n")

# static quality --------------------------------------------------------------------------------------------------------
Q = [("pylint_issues", "问题数 $\\downarrow$", 2, min), ("pylint_score", "得分 $\\uparrow$", 2, max), ("issues_per_100sloc", "每百行问题数 $\\downarrow$", 2, min),
     ("cc", "圈复杂度 $\\downarrow$", 2, min), ("mi", "可维护性 MI $\\uparrow$", 1, max), ("sloc", "SLOC", 1, None)]
qs = {m: AGG[m]["quality"]["correct"] for m in MAIN}
lines = []
for m in MAIN:
    q = qs[m]
    cells = [SHORT[m], str(q["n"])]
    for k, _, nd, best in Q:
        v = q[k]
        b = best([qs[x][k] for x in MAIN]) if best else None
        cells.append(("\\textbf{%s}" if b is not None and abs(v - b) < 1e-9 else "%s") % f(v, nd))
    lines.append(" & ".join(cells) + " \\\\")
write("quality.tex", "\\begin{tabular}{@{}lrrrrrrr@{}}\n\\toprule\n & & \\multicolumn{3}{c}{Pylint 3.3.5} & \\multicolumn{3}{c}{Radon 6.0.1} \\\\\n\\cmidrule(lr){3-5}\\cmidrule(lr){6-8}\n模型 & 答案数 & "
      + " & ".join(n for _, n, _, _ in Q) + " \\\\\n\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")

# usage and cost --------------------------------------------------------------------------------------------------------
lines = []
for t in TIERS + ["all"]:
    rr = []
    for m in (models_in(t) if t != "all" else [KIMI, HIGH, DS, MM]):
        u = U[m][t]
        cps = u.get("cost_per_solved")
        rr.append([SHORT[m], str(u["calls"]), f"{u['out_sum'] / 1e6:.2f}M", f"{u['out_mean'] / 1000:.1f}k", f(u["tps_median"]), f(u["ttft_median"]),
                   f"{u['lat_median']:.0f}", f"\\${u['cost']:.2f}", "--" if t == "L5" or not cps else f"\\${cps:.3f}"])
    lines.append(("合计" if t == "all" else t, rr))
TN["合计"] = "合计"
write("cost.tex", "\\begin{tabular}{@{}llrrrrrrrr@{}}\n\\toprule\n档位 & 模型 & 调用数 & 输出 token $\\downarrow$ & 每次输出 $\\downarrow$ & 输出速度（tokens/s）$\\uparrow$ & 首个 token（秒）$\\downarrow$ & 延迟中位数（秒）$\\downarrow$ & 费用 $\\downarrow$ & 每份解出答案 $\\downarrow$ \\\\\n\\midrule\n"
      + block(lines, 10) + "\n\\bottomrule\n\\end{tabular}\n")

# appendix: per-sample effort --------------------------------------------------------------------------------------------
lines = []
for t in ("L4", "L5"):
    for q, h, mx in e[t]["samples"]:
        qid = q.replace("#0", "") if t == "L5" else q.replace("#", "\\#")  # outside the f-string: Python 3.11 allows no backslash in one
        lines.append(f"{qid} & {t} & {h:.1f} & {mx:.1f} & {sgn(mx - h)} \\\\")
write("effort_samples.tex", "\\begin{longtable}{@{}llrrr@{}}\n\\toprule\n采样 & 档位 & high 得分 $\\uparrow$ & max 得分 $\\uparrow$ & 变化 \\\\\n\\midrule\\endhead\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{longtable}\n")
print("tables:", sorted(os.listdir(OUT)))
