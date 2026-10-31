"""LaTeX tables of the ladder technical report, generated from analysis.json so that no number is copied by hand.
Rows are tiers (or subsets), columns are metrics, every metric column carries its direction.

  python make_tables.py <paper dir>      -> <paper dir>/tables/*.tex
"""
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(ROOT, "analysis.json")))
OUT = os.path.join(ROOT, "tables")
os.makedirs(OUT, exist_ok=True)
TIERS = A["tiers"]
CLOSED = TIERS[:4]
TIER_NAME = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式"}
ORDER = A["models"]
NAME = A["names"]
SHORT = {"deepseek-flash": "DeepSeek", "MiniMax-M3.1-Flash": "MiniMax"}


def write(name, s):
    open(os.path.join(OUT, name), "w").write(s.strip() + "\n")


def f1(x, na="--"):
    return na if x is None else f"{x:.1f}"


def sg(x):
    """signed number with a typeset minus"""
    return f"{x:+.1f}".replace("-", "$-$")


def best(vals, higher=True):
    """bold the better of the two models (ties: neither)"""
    r = [round(v, 1) if v is not None else None for v in vals]
    if None in r or r[0] == r[1]:
        return ["%s"] * 2
    i = r.index(max(r) if higher else min(r))
    return [r"\textbf{%s}" if j == i else "%s" for j in range(2)]


def tier_block(t, cells):
    """one tier as two model rows, the tier name spanning both"""
    return (r"\multirow{2}{*}{" + TIER_NAME[t] + "} & " + SHORT[ORDER[0]] + " & " + cells[0] + r" \\" + "\n"
            + " & " + SHORT[ORDER[1]] + " & " + cells[1] + r" \\")


# ---------------------------------------------------------------- main results per tier
rows = []
for t in TIERS:
    T = {m: A["tier"][m][t] for m in ORDER}
    cols = []
    for key, hi in (("pass1", True), ("pass1_strict", True), ("score", True), ("score_strict", True), ("passn", True)):
        v = [T[m][key] if not (t == "L5" and key in ("pass1", "pass1_strict", "passn")) else None for m in ORDER]
        if key == "passn" and T[ORDER[0]]["n_per_problem"] == 1:
            v = [None, None]
        cols.append([mk % f1(x) if x is not None else "--" for mk, x in zip(best(v, hi), v)])
    ci = [A["ci"][m][t]["score" if t == "L5" else "pass1"] for m in ORDER]
    cells = [f"{T[m]['problems']} & {T[m]['samples']} & " + " & ".join(c[k] for c in cols) +
             r" & {\scriptsize\color{gray}%.1f--%.1f}" % tuple(ci[k]) for k, m in enumerate(ORDER)]
    rows.append(tier_block(t, cells))
    rows.append(r"\midrule" if t != TIERS[-1] else "")
tot = {m: {k: sum(A["tier"][m][t][k] * A["tier"][m][t]["samples"] for t in CLOSED) / sum(A["tier"][m][t]["samples"] for t in CLOSED)
           for k in ("pass1", "pass1_strict")} for m in ORDER}
mk = {k: best([tot[m][k] for m in ORDER]) for k in ("pass1", "pass1_strict")}
cells = [f"{sum(A['tier'][m][t]['problems'] for t in CLOSED)} & {sum(A['tier'][m][t]['samples'] for t in CLOSED)} & "
         f"{mk['pass1'][k] % f1(tot[m]['pass1'])} & {mk['pass1_strict'][k] % f1(tot[m]['pass1_strict'])} & -- & -- & -- & "
         r"{\scriptsize\color{gray}%.1f--%.1f}" % tuple(A["ci"][m]["L1-L4"]["pass1"]) for k, m in enumerate(ORDER)]
rows.append(r"\midrule")
rows.append((r"\multirow{2}{*}{L1--L4 合计} & " + SHORT[ORDER[0]] + " & " + cells[0] + r" \\" + "\n"
             + " & " + SHORT[ORDER[1]] + " & " + cells[1] + r" \\"))
write("main_results.tex", r"""
\begin{tabular}{llrrrrrrrr}
\toprule
 & & & & \multicolumn{2}{c}{pass@1（\%）$\uparrow$} & \multicolumn{2}{c}{平均得分 $\uparrow$} & & \\
\cmidrule(lr){5-6}\cmidrule(lr){7-8}
档位 & 模型 & 题数 & 采样数 & 宽时限 & 官方时限 & 宽时限 & 官方时限 & pass@$n$（\%）$\uparrow$ & 95\% 区间 \\
\midrule
""" + "\n".join(r for r in rows if r) + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- paired differences per tier
rows = []
for g in TIERS + ["L1-L4"]:
    w = A["wtl"][g]
    cells = []
    for k in ("pass1", "score"):
        if k in A["diff"][g]:
            d = A["diff"][g][k]
            sig = d["ci"][0] > 0 or d["ci"][1] < 0
            cells.append(f"{sg(d['diff'])}{'$^{*}$' if sig else ''} & [{sg(d['ci'][0])}, {sg(d['ci'][1])}]")
        else:
            cells.append("-- & --")
    p = w["p"]
    rows.append(("L1--L4 合计" if g == "L1-L4" else TIER_NAME[g]) + " & " + " & ".join(cells) +
                f" & {w['deepseek_better']} / {w['tie']} / {w['minimax_better']} & " +
                ("$<0.001$" if p < 0.001 else f"{p:.3f}") + r" \\")
write("pairwise.tex", r"""
\begin{tabular}{lrrrrrr}
\toprule
 & \multicolumn{2}{c}{pass@1 差（百分点）} & \multicolumn{2}{c}{平均得分差} & & \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
档位 & 差值 & 95\% 区间 & 差值 & 95\% 区间 & 逐题 DeepSeek 更好 / 持平 / MiniMax 更好 & 符号检验 $p$ \\
\midrule
""" + "\n".join(rows[:-1]) + "\n\\midrule\n" + rows[-1] + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- 2026 subset vs USACO
rows = []
sub_name = {"2026": "EGOI 2026（新题）", "USACO 2024-25": "USACO 2024--25", "USACO 2025-26": "USACO 2025--26"}
for t in ("L3", "L4"):
    for s in ("2026", "USACO 2024-25", "USACO 2025-26"):
        key = f"{t}|{s}"
        if key not in A["subsets"][ORDER[0]]:
            continue
        S = {m: A["subsets"][m][key] for m in ORDER}
        mk = best([S[m]["pass1"] for m in ORDER])
        mk2 = best([S[m]["score"] for m in ORDER])
        rows.append(f"{TIER_NAME[t]} & {sub_name[s]} & {S[ORDER[0]]['problems']} & " +
                    " & ".join(mk[k] % f1(S[m]["pass1"]) for k, m in enumerate(ORDER)) + " & " +
                    " & ".join(mk2[k] % f1(S[m]["score"]) for k, m in enumerate(ORDER)) + r" \\")
write("subsets.tex", r"""
\begin{tabular}{llrrrrr}
\toprule
 & & & \multicolumn{2}{c}{pass@1（\%，宽时限）$\uparrow$} & \multicolumn{2}{c}{平均得分 $\uparrow$} \\
\cmidrule(lr){4-5}\cmidrule(lr){6-7}
档位 & 子集 & 题数 & DeepSeek & MiniMax & DeepSeek & MiniMax \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- efficiency and complexity
rows = []
for t in CLOSED:
    cells = []
    for m in ORDER:
        T = A["tier"][m][t]
        c = A["complexity"][m][t]["time"]["classes"]
        cells.append(f"{T['perf_n']} & {T['perf_geo']:.2f}$\\times$ & {T['perf_faster']} & {T['perf_2x']} & {T['mem_geo']:.2f}$\\times$ & "
                     f"{c.get('better', 0)} / {c.get('same', 0)} / {c.get('worse', 0)} / {c.get('uncertain', 0)}")
    rows.append(tier_block(t, cells))
    rows.append(r"\midrule" if t != CLOSED[-1] else "")
write("efficiency.tex", r"""
\begin{tabular}{llrrrrrl}
\toprule
档位 & 模型 & 比较的答案数 & CPU 时间倍数 $\downarrow$ & 快于官方解 & 慢 2 倍以上 & 峰值内存倍数 $\downarrow$ & 时间复杂度：更优 / 同阶 / 更差 / 不确定 \\
\midrule
""" + "\n".join(r for r in rows if r) + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- failure types
KINDS = [("no code", "无代码"), ("timeout", "生成超时"), ("CE", "编译错误"), ("WA", "答案错误"), ("partial", "部分分"),
         ("RE", "运行错误"), ("TLE", "超时"), ("MLE", "超内存"), ("slow", "只在官方时限下超时")]
seen = {k for m in ORDER for t in TIERS for k in A["tier"][m][t]["fails"]}
unknown = seen - {k for k, _ in KINDS}
assert not unknown, f"failure kinds without a label: {unknown}"
kinds = [(k, n) for k, n in KINDS if k in seen]
rows = []
for t in TIERS:
    cells = [f"{A['tier'][m][t]['samples']} & " + " & ".join(str(A["tier"][m][t]["fails"].get(k, 0)) for k, _ in kinds) for m in ORDER]
    rows.append(tier_block(t, cells))
    rows.append(r"\midrule" if t != TIERS[-1] else "")
write("failures.tex", r"""
\begin{tabular}{ll*{""" + str(len(kinds) + 1) + r"""}{r}}
\toprule
档位 & 模型 & 答案数 & """ + " & ".join(n for _, n in kinds) + r""" \\
\midrule
""" + "\n".join(r for r in rows if r) + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- static quality (L1-L2, Python)
Q = {m: A["quality"][m]["correct"] for m in ORDER}
cols = [("n", "答案数", None, "{:.0f}"), ("pylint_issues", r"Pylint 问题数 $\downarrow$", False, "{:.2f}"),
        ("pylint_score", r"Pylint 得分 $\uparrow$", True, "{:.2f}"), ("issues_per_100sloc", r"每百行问题数 $\downarrow$", False, "{:.2f}"),
        ("cc", r"圈复杂度 $\downarrow$", False, "{:.2f}"), ("mi", r"可维护性 MI $\uparrow$", True, "{:.1f}"), ("sloc", "SLOC", None, "{:.1f}")]
rows = []
for k, m in enumerate(ORDER):
    cells = []
    for key, _, hi, fmt in cols:
        v = [Q[x][key] for x in ORDER]
        mk = best(v, hi)[k] if hi is not None else "%s"
        cells.append(mk % fmt.format(Q[m][key]))
    rows.append(f"{NAME[m]} & " + " & ".join(cells) + r" \\")
write("quality.tex", r"""
\begin{tabular}{l*{""" + str(len(cols)) + r"""}{r}}
\toprule
模型 & """ + " & ".join(h for _, h, _, _ in cols) + r""" \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}""")

# ---------------------------------------------------------------- usage and cost per tier
rows = []
for t in TIERS:
    cells = []
    U = {m: A["usage"][m]["per_tier"][t] for m in ORDER}
    for m in ORDER:
        solved = A["tier"][m][t]["pass1"] * A["tier"][m][t]["samples"] / 100 if t != "L5" else None
        cells.append(f"{U[m]['calls']} & {U[m]['completion'] / 1e6:.2f}M & {U[m]['completion'] / U[m]['calls'] / 1000:.1f}k & "
                     f"{U[m]['latency_median']:.0f} & \\${U[m]['cost']:.2f} & " +
                     (f"\\${U[m]['cost'] / solved:.3f}" if solved else "--"))
    rows.append(tier_block(t, cells))
    rows.append(r"\midrule")
for k, m in enumerate(ORDER):
    U = A["usage"][m]
    rows.append((r"\multirow{2}{*}{合计} & " if k == 0 else " & ") + f"{SHORT[m]} & {U['calls']} & {U['completion'] / 1e6:.2f}M & "
                f"{A['out_per_call'][m] / 1000:.1f}k & {U['latency']['median']:.0f} & \\${U['cost']:.2f} & "
                f"\\${A['cost_per_solved'][m]:.3f}" + r" \\")
write("usage.tex", r"""
\begin{tabular}{llrrrrrr}
\toprule
档位 & 模型 & 调用数 & 输出 token $\downarrow$ & 每次输出 $\downarrow$ & 延迟中位数（秒）$\downarrow$ & 费用 $\downarrow$ & 每份解出答案 $\downarrow$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}""")
# ---------------------------------------------------------------- vendor claims against the observations
DS, MM = ORDER


def dci(g, k):
    """DeepSeek - MiniMax on group g, metric k, with its paired-bootstrap interval"""
    d = A["diff"][g][k]
    lo, hi = sorted(-x for x in d["ci"])
    return f"{sg(-d['diff'])} [{sg(lo)}, {sg(hi)}]"


U = A["usage"]
rows = {
    DS: [
        ("Codeforces 评分 3471（内部评测，max 深度），高于 V4-Flash 的 3289 与 V4-Pro 的 3348", "竞赛编程",
         f"pass@1 领先 MiniMax：L1--L4 合计 {dci('L1-L4', 'pass1')}，L3 {dci('L3', 'pass1')}，L4 {dci('L4', 'pass1')}",
         "一致，可归因（相对 MiniMax）"),
        ("1017 版以自反馈强化学习改进端到端项目开发；智能体编程（DeepSWE v1.1 77.0、Terminal-Bench 4.0 42.3）", "多轮、多文件编程",
         "本文为单轮、单文件、无工具的作答", "本文未测"),
        ("1017 版缩短输出长度与任务耗时（相对 0910 版）", "—",
         f"每次调用平均输出 {A['out_per_call'][DS] / 1000:.1f}k token，短于 MiniMax 的 {A['out_per_call'][MM] / 1000:.1f}k；没有 0910 版对照", "无法检验"),
        ("按思考深度施加长度惩罚、深度可调", "思考深度",
         "本文使用接口默认的 high，未比较不同深度", "本文未测"),
    ],
    MM: [
        ("推理速度：输出可达每秒 200 token 以上、中位数 170 以上", "生成速度",
         f"首个 token 之后的平均生成速度 {A['gen_speed'][MM]:.0f} token/s，低于所称；DeepSeek 为 {A['gen_speed'][DS]:.0f}",
         "不一致（国内站、8 路并发）"),
        ("智能体编程与工具调用（DeepSWE v1.1 73.7、Terminal Bench 4.0 38.1）；交错思考", "多轮、多文件编程",
         "本文为单轮、单文件、无工具的作答", "本文未测"),
        ("在线推理快近 3 倍、使用成本降低 70\\%（相对前代）", "—",
         f"没有前代对照；本文费用 \\${U[MM]['cost']:.2f}，高于 DeepSeek 的 \\${U[DS]['cost']:.2f}", "无法检验"),
        ("没有竞赛编程方面的声称或成绩", "竞赛编程",
         "L3、L4 的 pass@1 均显著落后 DeepSeek（见上）", "无对应声称"),
    ],
}
body = []
for m in ORDER:
    body.append(r"\multicolumn{4}{@{}l}{\textbf{" + NAME[m] + r"}} \\")
    body += [f"{a} & {b} & {c} & {d} \\\\" for a, b, c, d in rows[m]]
    body.append(r"\midrule" if m != ORDER[-1] else "")
write("attribution.tex", r"""
\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}p{4.3cm}>{\raggedright\arraybackslash}p{1.7cm}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{2.3cm}@{}}
\toprule
厂商声称 & 对应维度 & 本文观测（DeepSeek $-$ MiniMax，95\% 区间） & 判定 \\
\midrule
""" + "\n".join(x for x in body if x) + r"""
\bottomrule
\end{tabularx}""")
print("tables:", sorted(os.listdir(OUT)))
