"""Build quality.tex (static code quality, the protocol of arXiv:2610.19167) from quality/<model>.jsonl, the
output of `cb quality <run dir> [--sonar]`. site.py imports this module for the same tables.

Three tables, as in the paper: per-answer means over all answers, over correct ones (both by difficulty), and the
correct-only densities per 100 SLOC (sum of counts / sum of SLOC x 100). No composite score.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = [("kimi-k3.1-pro", "Kimi K3.1 Pro", "Kimi"), ("deepseek-flash", "DeepSeek-V4.1-Flash", "DS-Flash"),
          ("deepseek-v4-pro", "DeepSeek-V4-Pro", "DS-Pro")]
DIFFS = [("medium", "中等"), ("hard", "困难"), (None, "合计")]
# quality/<model>.jsonl: copies of runs/<model>/livecodebench-lcb_newest35-full/quality.jsonl from the server
Q = {m: [json.loads(l) for l in open(os.path.join(HERE, "quality", m + ".jsonl"))] for m, *_ in MODELS}
SONAR = all(r.get("sonar") is not None for rs in Q.values() for r in rs)

# (header, value of one answer); None values (a Pylint score of a file that does not parse) are left out of means
ISSUES = [("Pylint 合计", lambda r: r["pylint"]["total"]), ("C", lambda r: r["pylint"]["convention"]),
          ("R", lambda r: r["pylint"]["refactor"]), ("W", lambda r: r["pylint"]["warning"]),
          ("E", lambda r: r["pylint"]["error"]), ("得分", lambda r: r["pylint"]["score"])]
SONAR_COLS = [("可维护性", lambda r: r["sonar"]["maintainability"]), ("可靠性", lambda r: r["sonar"]["reliability"]),
              ("安全", lambda r: r["sonar"]["security"])]
RADON = [("CC", lambda r: r["radon"]["complexity"]), ("MI", lambda r: r["radon"]["mi"]),
         ("Func", lambda r: r["radon"]["functions"]), ("LOC", lambda r: r["radon"]["loc"]),
         ("LLOC", lambda r: r["radon"]["lloc"]), ("SLOC", lambda r: r["radon"]["sloc"]),
         ("CMT", lambda r: r["radon"]["comments"]), ("BLN", lambda r: r["radon"]["blank"])]
DENSITY = ISSUES[:5] + [("CC", RADON[0][1]), ("Func", RADON[2][1])] + (SONAR_COLS if SONAR else [])


def group(m, d, correct):
    return [r for r in Q[m] if r["radon"] and (not correct or r["passed"]) and (d is None or r["difficulty"] == d)]


def mean(rs, f):
    v = [f(r) for r in rs if f(r) is not None]
    return statistics.mean(v) if v else None


def density(rs, f):
    sloc = sum(r["radon"]["sloc"] for r in rs)
    return 100 * sum(f(r) for r in rs) / sloc if sloc else None


def rows(cols, correct, agg=mean):
    """[(model short name, difficulty name, n, [values])] for every model x difficulty."""
    out = []
    for m, _, name in MODELS:
        for d, dn in DIFFS:
            rs = group(m, d, correct)
            out.append((name, dn, len(rs), [agg(rs, f) for _, f in cols]))
    return out


def best(table, col, low=True):
    """The best value of a column among the 合计 rows (lowest, or highest when low=False)."""
    vals = [v[col] for _, dn, _, v in table if dn == "合计" and v[col] is not None]
    return (min if low else max)(vals) if vals else None


ISSUE_COLS = ISSUES + (SONAR_COLS if SONAR else [])
HIGHER_BETTER = {"得分", "MI"}


def tex_rows(table, cols, nd=2):
    L = []
    bests = [best(table, i, low=h not in HIGHER_BETTER) for i, (h, _) in enumerate(cols)]
    for i, (name, dn, n, vals) in enumerate(table):
        cells = []
        for j, v in enumerate(vals):
            s = "—" if v is None else f"{v:.{nd}f}"
            if dn == "合计" and v is not None and bests[j] is not None and round(v, nd) == round(bests[j], nd) \
                    and cols[j][0] not in ("LOC", "LLOC", "SLOC", "CMT", "BLN", "Func"):
                s = f"\\textbf{{{s}}}"
            cells.append(s)
        head = (name if dn == "中等" else "") + f" & {dn} & {n}"
        L.append(head + " & " + " & ".join(cells) + " \\\\" + ("\\midrule" if dn == "合计" and i < len(table) - 1 else ""))
    return "\n".join(L)


T_ISSUES_ALL, T_ISSUES_OK = rows(ISSUE_COLS, False), rows(ISSUE_COLS, True)
T_RADON_ALL, T_RADON_OK = rows(RADON, False), rows(RADON, True)
T_DENSITY = rows(DENSITY, True, density)

def tex_table(blocks, cols, nd, groups):
    """A full tabular: blocks = [(label or None, rows)], groups = [(title, number of columns)] over the value columns."""
    n = 3 + len(cols)
    L = ["\\begin{tabular}{@{}llr" + "r" * len(cols) + "@{}}", "\\toprule"]
    if groups:
        L.append(" & & & " + " & ".join(f"\\multicolumn{{{k}}}{{c}}{{{t}}}" for t, k in groups) + " \\\\")
        pos, rules = 4, []
        for t, k in groups:
            rules.append(f"\\cmidrule(lr){{{pos}-{pos + k - 1}}}")
            pos += k
        L.append("".join(rules))
    L.append("模型 & 难度 & 份数 & " + " & ".join(h for h, _ in cols) + " \\\\")
    L.append("\\midrule")
    for bi, (label, table) in enumerate(blocks):
        if bi:
            L.append("\\midrule")
        if label:
            L.append(f"\\multicolumn{{{n}}}{{@{{}}l}}{{\\textit{{{label}}}}} \\\\")
        L.append(tex_rows(table, cols, nd))
    L += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(L)


ISSUE_GROUPS = [("Pylint", len(ISSUES))] + ([("SonarQube", len(SONAR_COLS))] if SONAR else [])
DENSITY_GROUPS = [("Pylint", 5), ("Radon", 2)] + ([("SonarQube", len(SONAR_COLS))] if SONAR else [])


def total(rs, key):
    return sum(r["pylint"]["messages"].get(key, 0) for r in rs)


def spread(rs, key):
    """(answers with the message, total count)."""
    return sum(1 for r in rs if r["pylint"]["messages"].get(key)), total(rs, key)


def bullets():
    """Comparison bullets as [(latex, html)], every number taken from the tables above."""
    ok = {m: group(m, None, True) for m, *_ in MODELS}
    short = {m: s for m, _, s in MODELS}
    K, F, P = (m for m, *_ in MODELS)

    def v(table, col, m):
        return next(vals[col] for name, dn, _, vals in table if name == short[m] and dn == "合计")

    def three(table, col, nd=2):
        return " / ".join(f"{v(table, col, m):.{nd}f}" for m in (K, F, P))

    nm = {m: total(ok[m], "C0103 invalid-name") for m in (K, F, P)}
    cell = {m: spread(ok[m], "W0640 cell-var-from-loop") for m in (K, F, P)}
    unused = {m: spread(ok[m], "W0612 unused-variable") for m in (K, F, P)}
    order = "Kimi / DS-Flash / DS-Pro"
    out = [
        (f"Pylint（{order}，每份）：问题 {three(T_ISSUES_OK, 0)}，得分 {three(T_ISSUES_OK, 5)}。DS-Pro 最多，主要是命名不合规"
         f"（C0103，共 {nm[K]} / {nm[F]} / {nm[P]} 条）。"),
        (f"警告（W）Kimi 每份 {v(T_ISSUES_OK, 3, K):.2f}，高于 DS-Flash 的 {v(T_ISSUES_OK, 3, F):.2f}，"
         f"但集中在 {cell[K][0]} 份答案的循环内闭包（W0640 {cell[K][1]} 条）；DS-Pro 的 W0640 有 {cell[P][1]} 条，"
         f"集中在 {cell[P][0]} 份。未使用的变量（W0612）：Kimi {unused[K][1]}、DS-Flash {unused[F][1]}、DS-Pro {unused[P][1]} 条。"),
        (f"Radon（每份）：Kimi 代码最短（SLOC {three(T_RADON_OK, 5, 1)}）、可维护性指数最高（{three(T_RADON_OK, 1, 1)}）、"
         f"圈复杂度最低（{three(T_RADON_OK, 0, 1)}）。"),
        (f"按每 100 SLOC：Pylint 问题 {three(T_DENSITY, 0)}，排序不变；但 Kimi 的圈复杂度密度（{three(T_DENSITY, 5)}）"
         f"和函数密度（{three(T_DENSITY, 6)}）最高，即代码更短、分支和函数更密。"),
    ]
    if SONAR:
        si = len(ISSUES)
        out.append(f"SonarQube（每份）：可维护性 {three(T_ISSUES_OK, si)}，可靠性 {three(T_ISSUES_OK, si + 1)}，安全 {three(T_ISSUES_OK, si + 2)}。")
    return [(t.replace("_", "\\_"), t) for t in out]


if __name__ == "__main__":
    L = []

    def mac(name, body):
        L.append(f"\\newcommand{{\\{name}}}{{%\n{body}}}")

    mac("QualIssueTable", tex_table([("全部答案", T_ISSUES_ALL), ("仅通过的答案", T_ISSUES_OK)], ISSUE_COLS, 2, ISSUE_GROUPS))
    mac("QualRadonTable", tex_table([("全部答案", T_RADON_ALL), ("仅通过的答案", T_RADON_OK)], RADON, 1, None))
    mac("QualDensityTable", tex_table([(None, T_DENSITY)], DENSITY, 2, DENSITY_GROUPS))
    L.append(f"\\newcommand{{\\QualSonar}}{{{'1' if SONAR else '0'}}}")
    mac("QualBullets", "\n".join(f"  \\item {t}" for t, _ in bullets()))
    open(os.path.join(HERE, "quality.tex"), "w").write("\n".join(L) + "\n")
    for t, cols in ((T_ISSUES_OK, ISSUE_COLS), (T_RADON_OK, RADON), (T_DENSITY, DENSITY)):
        print(" | ".join(h for h, _ in cols))
        for name, dn, n, v in t:
            if dn == "合计":
                print(name, n, " ".join("—" if x is None else f"{x:.2f}" for x in v))
