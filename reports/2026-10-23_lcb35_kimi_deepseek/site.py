"""Build the public results site (GitHub Pages) for this report: python site.py <out dir>.

Every number comes from gen.py and perfgen.py (imported, so the site matches report.pdf). The output is plain
HTML with relative links (Pages serves it under /<repo>/), Pygments-highlighted code, inline SVG charts and no
external resources, since CDNs are unreliable from China. Problem statements are not reproduced: each problem
gets a one-line summary and a link to the original page. Needs pygments (the scratch lint venv has it).
"""
import html
import json
import os
import shutil
import statistics
import sys

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

import gen
import perfgen

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(sys.argv[1])
DATE = "2026-10-23"
MODELS = [(k, name, short) for k, name, short, _ in gen.MODELS]
CLS = {"kimi-k3.1-pro": "kimi", "deepseek-flash": "flash", "deepseek-v4-pro": "pro"}
P, R, N = gen.problems, gen.R, len(gen.problems)
ORDER = gen.ORDER
ST = {(r["model"], r["q"]): r for r in perfgen.static}
MARK = {"$^{*}$": "*", "$^{\\dagger}$": "†"}
esc = html.escape

# One-line summaries written from the statements (which are not published here).
SUMMARY = {
    "3717": "每次可把一个元素加 1 或减 1；求最少操作次数，使数组中出现至少 k 个互不重叠、长度恰为 x 且元素全部相等的子数组。",
    "3744": "每个查询 [l, r] 对应数组 l, l+1, …, r；每次操作选两个数，各自替换为除以 4 向下取整的结果；求每个查询把所有数变为 0 的最少操作数，输出总和。",
    "3765": "把数组划分为若干子数组，第 i 段的代价为（到该段末尾的前缀和 + k·i）×（该段 cost 之和）；求最小总代价。",
    "3777": "找一个交错和等于 k 的非空子序列，使其元素乘积在不超过 limit 的前提下最大；不存在时返回 -1。",
    "3784": "对每个下标 i，删去第 i 个字符串后，从剩余字符串中任选 k 个，求它们最长公共前缀的最大长度。",
    "3793": "从 s 取一个子串、从 t 取一个子串，按顺序拼接（均可为空）；求能得到的最长回文串长度。",
    "3801": "各位数字之积能被各位数字之和整除的正整数称为美丽数；求 [l, r] 内美丽数的个数。",
    "3805": "对 01 串至多做一次交易：先把一段两侧都是 0 的连续 1 全变成 0，再把一段两侧都是 1 的连续 0 全变成 1；求最终 1 的最大个数。",
    "3809": "两行属性中共同出现的不同整数个数不少于 k 时连一条边；求所得无向图的连通分量数。",
    "abc397_d": "给定正整数 N，判断是否存在正整数 x、y 使 x³ − y³ = N；存在则输出一组。",
    "abc397_e": "判断一棵 NK 个顶点的树能否划分为 N 条路径，每条恰含 K 个顶点。",
    "abc397_f": "把序列切成三段非空的连续子数组，使三段各自不同元素个数之和最大。",
    "abc397_g": "有向图中恰选 K 条边把权值设为 1，其余为 0；求顶点 1 到 N 最短距离的最大可能值。",
    "abc398_b": "七张牌中能否选出五张组成葫芦（三张相同加另外两张相同）。",
    "abc398_c": "在“所持整数与其他人都不同”的人中，找出整数最大者的编号；没有这样的人时按要求报告。",
    "abc398_d": "烟雾按给定的风向序列逐步整体平移，原点无烟时重新生成；对每个时刻判断指定格子上是否有烟。",
    "abc398_f": "输出一个以 S 为前缀的最短回文串。",
    "abc398_g": "在不含奇环的图上，两人轮流加一条新边且加边后不能出现奇环，无法操作者输；判断双方最优时谁获胜。",
    "abc399_c": "求最少删除多少条边，使无向图变成森林。",
    "abc399_d": "2N 个座位坐着 N 对情侣；统计有多少组两对情侣（两对原本都不相邻），只在这四人之间交换座位就能让两对都相邻。",
    "abc399_e": "每次操作把 S 中某个字母全部替换成另一个字母；判断能否把 S 变成 T，能则求最少操作次数。",
    "abc399_f": "求所有子数组元素和的 K 次方之和，模 998244353。",
    "abc400_c": "能写成 2ᵃ·b²（a、b 为正整数）的数称为好数；求 1 到 N 内好数的个数，N ≤ 10¹⁸。",
    "abc400_d": "网格中可以走到相邻道路格，也可以向一个方向前踢，打通前方至多两格内的墙；求从起点到终点的最少前踢次数。",
    "abc400_e": "恰有两个不同质因数、且每个质因数的指数都是偶数的数称为 400 数；对每个查询 A，求不超过 A 的最大 400 数。",
    "abc400_g": "N 个蛋糕各有三项属性，从中组成 K 对，每对的价格是两者三项属性分别相加后的最大值；求 K 对总价格的最大值。",
    "arc195_a": "判断序列 B 是否至少以两种不同的位置组合作为 A 的子序列出现。",
    "arc195_b": "A、B 中的 -1 可替换为任意非负整数，A 可任意重排；判断能否使所有 Aᵢ + Bᵢ 相等。",
    "arc195_c": "R 个红子（横竖走一步）和 B 个蓝子（斜走一步）摆上棋盘，使每个棋子一步能走到下一个、最后一个能走回第一个；判断能否做到并给出一种摆法。",
    "arc195_d": "可以交换相邻元素，或删除开头一段全部相等的前缀；求删空序列的最少操作数。",
    "arc195_e": "顶点 i 的父节点在 1…i−1 中任选，共 (N−1)! 棵带权树；对每个查询求 u、v 两点距离在所有树上的总和，模 998244353。",
    "arc196_a": "反复删除两个相邻的数并得到二者之差的绝对值，直到长度不超过 1；求总得分最大值。",
    "arc196_b": "每格瓷砖画有一段拐角线或直线，可以旋转；把网格看作环面，求线段处处没有断头的摆法数，模 998244353。",
    "arc196_c": "2N 个点依次连有向边，每个白点与一个黑点配对并从白点连边到黑点；求使整张图强连通的配对方案数，模 998244353。",
    "arc196_d": "一排 N 个城镇之间的道路可设任意整数权值，每人从 Sᵢ 走到 Tᵢ，要求出发和到达时体力恰为 0、途中始终为正；对每个查询区间判断能否同时满足这些人的要求。",
}
# The three examples of report.pdf, with the points it states.
EXAMPLE = {
    "abc400_c": "好数恰为 2m² 或 4m² 两类且互不重叠，答案为 ⌊√(N/2)⌋ + ⌊√(N/4)⌋；须用整数开方，浮点 sqrt 在 10¹⁸ 附近出错。",
    "arc195_d": "交换与删除的组合优化，须近线性时间（T ≤ 10⁵，ΣN ≤ 2×10⁵）。样例：(1,1,2,1,2) 为 3（1 次交换 + 2 次删除），(4,2,1,3) 为 4（不交换）。",
    "3801": "数位 DP：含 0 时积为 0，必满足；否则积为 2ᵃ3ᵇ5ᶜ7ᵈ，状态有限；暴力枚举超时。",
}
SMALL = {"to", "of", "with", "an", "a", "into", "the", "and", "in"}

REJ = {}
for line in open(os.path.join(HERE, "rejudge_atcoder.jsonl")):
    r = json.loads(line)
    if "model" in r:
        REJ[(r["model"], r["q"])] = ("校验器 " + r["checker"]) if "checker" in r else ("逐 token 比对 " + r["exact"])


def title(p):
    if p["platform"] == "atcoder":
        return p["question_title"]
    w = p["question_title"].split("-")
    return " ".join(x if i and x in SMALL else x.upper() if len(x) == 1 else x.capitalize() for i, x in enumerate(w))


def contest(p):
    c = p["contest_id"]
    if p["platform"] == "atcoder":
        return f"AtCoder {c[:3].upper()} {c[3:]} {p['question_id'].split('_')[1].upper()} 题"
    kind, num = c.rsplit("-", 1)
    return f"LeetCode {'双周赛' if kind.startswith('biweekly') else '周赛'} {num}"


def url(p):
    if p["platform"] == "atcoder":
        return f"https://atcoder.jp/contests/{p['contest_id']}/tasks/{p['question_id']}"
    return f"https://leetcode.com/problems/{p['question_title']}/"


def diff(p):
    return "中等" if p["difficulty"] == "medium" else "困难"


def lcb_reason(r):
    if not r["code_list"][0].strip():
        return "无代码"
    try:
        return gen.ERR.get(json.loads(r["metadata"][0]).get("error_code"), "其他错误")
    except (ValueError, IndexError, TypeError):
        return "其他错误"


def verdict(k, q):
    """(css class, short mark) for the corrected verdict."""
    m = R[k]
    if m["passed"][q]:
        return "ok", "✓" + MARK.get(m["mark"].get(q), "")
    return "bad", "✗"


def perf(k, q):
    """(max-test CPU s, peak MB, ratio to the fastest) or None when the problem is not measurable."""
    d = perfgen.prob.get(q, {})
    if q not in perfgen.measurable or k not in d:
        return None
    best = min(v[0] for v in d.values())
    return d[k][0], d[k][2] / 1024, d[k][0] / best if best > 0 else 1.0


def dot(k):
    return f'<span class="dot {CLS[k]}"></span>'


def mname(name, short):
    return f'<span class="long">{name}</span><span class="short">{short}</span>'


def ktok(n):
    return gen.ktok(n)


def money(v, nd=2):
    return f"${v:.{nd}f}"


# ---------------------------------------------------------------- aggregates used across pages
S = {}
for k, name, short in MODELS:
    m = R[k]
    S[k] = {
        "pass": sum(m["passed"].values()),
        "lcb": sum(m["lcb"].values()),
        "lat": statistics.median(m["lat"].values()),
        "speed": statistics.median(m["out"][q] / m["lat"][q] for q in m["lat"] if m["lat"][q] > 0),
        "cost": m["cost"],
        "gm": perfgen.agg[k][0],
    }
    S[k]["per"] = S[k]["cost"] / max(1, S[k]["pass"])
judge_fix = sum(R[k]["passed"][q] and not R[k]["lcb"][q] and (k, q) not in gen.USER_VERIFIED for k, *_ in MODELS for q in P)
api_fix = sum((k, q) in gen.USER_VERIFIED and not R[k]["lcb"][q] for k, *_ in MODELS for q in P)
real_fail = sum(not R[k]["passed"][q] for k, *_ in MODELS for q in P)
raw_fail = sum(not R[k]["lcb"][q] for k, *_ in MODELS for q in P)
assert raw_fail == judge_fix + api_fix + real_fail
KF, FL, PR = "kimi-k3.1-pro", "deepseek-flash", "deepseek-v4-pro"


# ---------------------------------------------------------------- page frame
NAV = [("index.html", "概览"), ("problems.html", "题目"), ("method.html", "原理"), ("results.html", "结果")]


def page(path, title_, body, desc, extra_css=""):
    depth = path.count("/")
    up = "../" * depth
    links = "".join(f'<li><a href="{up}{h}"{" aria-current=\"page\"" if h == path else ""}>{t}</a></li>' for h, t in NAV)
    css = f'<link rel="stylesheet" href="{up}assets/style.css">' + (
        f'<link rel="stylesheet" href="{up}assets/{extra_css}">' if extra_css else "")
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title_)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="icon" href="{up}assets/icon.svg" type="image/svg+xml">
{css}
</head>
<body>
<nav class="nav"><div class="nav-in"><a class="brand" href="{up}index.html">BAI AI Lab 代码评测</a><ul>{links}</ul></div></nav>
<main>
{body}
</main>
<footer><div class="wrap">
<p>BAI AI Lab 代码能力评测 · 数据截至 {DATE}（UTC）</p>
<p>评测框架 LiveCodeBench release_v6（ICLR 2025），运行与复核用 codingBench。题面版权归 AtCoder 与 LeetCode，本站只给出概述与原题链接。</p>
<p>全部数据：<a href="{up}data/lcb35.json">data/lcb35.json</a></p>
</div></footer>
<script src="{up}assets/app.js"></script>
</body>
</html>
"""
    dst = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write(doc)


def table(head, rows, cls=None):
    """head: [(text, css)], rows: list of lists of (html, css)."""
    th = "".join(f'<th class="{c}">{t}</th>' if c else f"<th>{t}</th>" for t, c in head)
    trs = []
    for row in rows:
        attrs = ""
        if isinstance(row, tuple):
            attrs, row = row
        tds = "".join(f'<td class="{c}">{t}</td>' if c else f"<td>{t}</td>" for t, c in row)
        trs.append(f"<tr{attrs}>{tds}</tr>")
    idattr = f' id="{cls}"' if cls else ""
    return f'<div class="tw"><table{idattr}><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def best_cells(vals, fmt, best):
    b = best(vals)
    return [(fmt(v), "n best" if v == b else "n") for v in vals]


MHEAD = [(f"{dot(k)} {mname(name, short)}", "n") for k, name, short in MODELS]


# ---------------------------------------------------------------- index (概览)
def specs(items):
    return '<ul class="specs">' + "".join(f"<li><b>{v}</b><span>{lab}</span></li>" for v, lab in items) + "</ul>"


def index():
    cols = []
    for k, name, short in MODELS:
        s = S[k]
        cols.append(f"""<div class="model"><div>{dot(k)}<h3>{mname(name, short)}</h3><div class="id">{k}</div></div>
<div class="big">{s['pass']}/{N}</div><div class="cap">复核后通过</div>
{specs([(f"{s['lcb']}/{N}", "LCB 原始判分"), (f"{s['lat']:.0f} 秒", "延迟"), (f"{s['speed']:.0f}", "输出 token/秒"),
        (money(s['cost']), "费用"), (money(s['per'], 3), "每道通过题费用"), (f"{s['gm']:.2f}×", "代码耗时 / 最快者")])}</div>""")
    nperf = len(perfgen.common)
    body = f"""<section class="hero"><div class="wrap">
<p class="eyebrow">LiveCodeBench · 最新 35 题 · {DATE}</p>
<h1>代码能力评测</h1>
<p class="lead"><span class="nw">Kimi K3.1 Pro</span>、<span class="nw">DeepSeek-V4.1-Flash</span>、<span class="nw">DeepSeek-V4-Pro</span>：正确率、速度、费用与代码性能。</p>
<div class="ctas"><a class="btn" href="results.html">查看结果</a><a class="more" href="method.html">评测原理</a><a class="more" href="problems.html">全部题目</a></div>
</div></section>
<section class="section alt"><div class="wrap">
<h2>三个模型</h2>
<p class="sub">LiveCodeBench release_v6 中最新的 35 道竞赛题（中等 10、困难 25），每题调用 1 次，判分经过复核。</p>
<div class="compare" style="--rows:9">{''.join(cols)}</div>
<p class="note">延迟、输出速度为每题中位数；费用按 token 计；代码耗时为 {len(perfgen.common)} 道可比题上相对最快者的几何平均倍数。</p>
</div></section>
<section class="section"><div class="wrap">
<h2>要点</h2>
<p class="sub">数字均来自本次评测记录，计算方法见“原理”。</p>
<div class="tiles">
<a class="card" href="method.html#rejudge"><p class="k">判分</p><p class="v">{raw_fail} → {real_fail}</p>
<p>LCB 原始判分共 {raw_fail} 个失败：{judge_fix} 个由判题程序或测试数据的问题造成，{api_fix} 个是 API 返回了与题目无关的内容（人工复核正确），真正答错的只有 {real_fail} 个（Kimi <code>abc398_g</code>）。</p><p class="more">复核方法</p></a>
<a class="card" href="results.html#overall"><p class="k">速度</p><p class="v">{S[FL]['lat']:.0f} 秒</p>
<p>DS-V4.1-Flash 每题延迟中位数；Kimi {S[KF]['lat']:.0f} 秒，DS-V4-Pro {S[PR]['lat']:.0f} 秒。输出速度中位数：Flash {S[FL]['speed']:.0f}、Pro {S[PR]['speed']:.0f}、Kimi {S[KF]['speed']:.0f} token/秒。</p></a>
<a class="card" href="results.html#cost"><p class="k">费用</p><p class="v">{money(S[FL]['per'], 3)}</p>
<p>DS-V4.1-Flash 每道通过题的费用；DS-V4-Pro {money(S[PR]['per'], 3)}，Kimi {money(S[KF]['per'], 3)}。总费用 {money(S[FL]['cost'])} / {money(S[PR]['cost'])} / {money(S[KF]['cost'])}。</p></a>
<a class="card" href="results.html#perf"><p class="k">代码性能</p><p class="v">{S[KF]['gm']:.2f}×</p>
<p>在 {nperf} 道能区分性能的题上，Kimi 代码的运行时间相对最快者的几何平均倍数；DS-V4.1-Flash {S[FL]['gm']:.2f}×，DS-V4-Pro {S[PR]['gm']:.2f}×。</p></a>
<div class="card wide"><p class="k">选型</p>
<p>只看通过率和成本，DS-V4.1-Flash 最优：满分，费用为 DS-V4-Pro 的 {100 * S[FL]['cost'] / S[PR]['cost']:.0f}%、Kimi 的 {100 * S[FL]['cost'] / S[KF]['cost']:.0f}%，延迟最低。看代码运行效率，Kimi K3.1 Pro 最好，但输出最慢、费用最高，且非流式长请求在余额不足时会挂起并照常扣费，须用流式加空闲超时调用。DS-V4-Pro 满分，但输出 token 最多、代码效率波动最大。</p></div>
</div>
</div></section>"""
    page("index.html", "代码能力评测 · BAI AI Lab", body,
         "Kimi K3.1 Pro、DeepSeek-V4.1-Flash、DeepSeek-V4-Pro 在 LiveCodeBench 最新 35 题上的评测结果")


# ---------------------------------------------------------------- problems (题目)
def problems():
    import collections
    dn = collections.Counter(P[q]["difficulty"] for q in P)
    grid = [[(d, "")] + [(str(sum(1 for q in P if P[q]["difficulty"] == dk and P[q]["platform"] == pk)), "n")
                         for pk in ("atcoder", "leetcode")] + [(str(dn[dk]), "n")]
            for d, dk in (("中等", "medium"), ("困难", "hard"))]
    grid.append([("合计", "")] + [(str(sum(1 for q in P if P[q]["platform"] == pk)), "n") for pk in ("atcoder", "leetcode")]
                + [(str(N), "n")])
    src = collections.Counter()
    for q in P:
        c = P[q]["contest_id"]
        src["AtCoder ABC" if c.startswith("abc") else "AtCoder ARC" if c.startswith("arc") else "LeetCode"] += 1
    abc = sorted({int(P[q]["contest_id"][3:]) for q in P if P[q]["contest_id"].startswith("abc")})
    arc = sorted({int(P[q]["contest_id"][3:]) for q in P if P[q]["contest_id"].startswith("arc")})
    dates = sorted(P[q]["contest_date"][:10] for q in P)
    srows = [[(f"AtCoder ABC {abc[0]}–{abc[-1]}", ""), (str(src["AtCoder ABC"]), "n"), ("完整程序，标准输入输出", "")],
             [(f"AtCoder ARC {arc[0]}–{arc[-1]}", ""), (str(src["AtCoder ARC"]), "n"), ("完整程序，标准输入输出", "")],
             [("LeetCode 周赛 / 双周赛", ""), (str(src["LeetCode"]), "n"), ("补全给定的 Python 函数", "")]]
    ex = []
    for q in ("abc400_c", "arc195_d", "3801"):
        p = P[q]
        res = "；".join(f"{short} <span class=\"{verdict(k, q)[0]}\">{verdict(k, q)[1]}</span> {R[k]['out'][q] / 1e3:.1f}k token"
                       for k, name, short in MODELS)
        ex.append(f"""<a class="card" href="p/{q}.html"><p class="k">{contest(p)} · {diff(p)}</p><h4>{esc(title(p))}</h4>
<p>{SUMMARY[q]}</p><p class="cap">{res}</p></a>""")
    rows = []
    for q in ORDER:
        p = P[q]
        cells = [(f'<a class="mono" href="p/{q}.html">{q}</a>', "nw"), (esc(title(p)), ""), (diff(p), "nw"),
                 (contest(p), "nw hide-sm"), (p["contest_date"][:10], "nw hide-sm")]
        for k, *_ in MODELS:
            c, t = verdict(k, q)
            cells.append((f'<span class="{c}">{t}</span>', "c"))
        rows.append((f' data-difficulty="{p["difficulty"]}" data-platform="{p["platform"]}" data-href="p/{q}.html"', cells))
    head = [("题号", ""), ("题目", ""), ("难度", ""), ("来源", "hide-sm"), ("日期", "hide-sm")] + \
           [(f'{dot(k)}<span class="hide-sm"> {short}</span>', "c") for k, name, short in MODELS]
    body = f"""<section class="section tight"><div class="wrap">
<h2>题目</h2>
<p class="sub">LiveCodeBench release_v6 最新 100 题中，按难度各取最新：中等 10、困难 25；比赛日期 {dates[0]} 至 {dates[-1]}。</p>
<div class="tiles">
<div>{table([("难度", ""), ("AtCoder", "n"), ("LeetCode", "n"), ("合计", "n")], grid)}</div>
<div>{table([("来源", ""), ("题数", "n"), ("形式", "")], srows)}</div>
</div>
<h3>示例</h3>
<div class="tiles">{''.join(ex)}</div>
<h3 id="all">全部 {N} 题</h3>
<div class="filters">
<div class="seg" data-filter="difficulty"><button aria-pressed="true" data-value="all">全部难度</button><button aria-pressed="false" data-value="medium">中等</button><button aria-pressed="false" data-value="hard">困难</button></div>
<div class="seg" data-filter="platform"><button aria-pressed="true" data-value="all">全部来源</button><button aria-pressed="false" data-value="atcoder">AtCoder</button><button aria-pressed="false" data-value="leetcode">LeetCode</button></div>
</div>
{table(head, rows, "plist")}
<p class="note">✓ 复核后通过；✓* LCB 判为失败、复核后通过；✓† API 返回与题目无关的内容，人工另行调用验证正确，按通过计；✗ 未通过。点击一行查看该题三个模型的结果与代码。</p>
</div></section>"""
    page("problems.html", "题目 · 代码能力评测", body, "LiveCodeBench 最新 35 题：分布、示例与逐题结果")


def problem_page(i, q):
    p = P[q]
    cols, tabs, panels, data = [], [], [], {}
    for j, (k, name, short) in enumerate(MODELS):
        m, r = R[k], R[k]["rows"][q]
        c, t = verdict(k, q)
        if (k, q) in gen.USER_VERIFIED:
            rej = "API 返回与题目无关的内容；人工另行调用验证正确，按通过计"
        elif p["platform"] == "leetcode":
            rej = "函数调用题，沿用 LCB 判分"
        else:
            rej = REJ.get((k, q), "—")
        lcb = "通过" if m["lcb"][q] else f"失败（{lcb_reason(r)}）"
        status = "通过" if m["passed"][q] else f"未通过：{m['why'][q]}"
        pf, st = perf(k, q), ST.get((k, q))
        if pf:
            cpu = f"{pf[0]:.2f} 秒" + (f"（{pf[2]:.1f}×）" if pf[2] >= 2 else "（最快）" if pf[2] == 1 else "")
            mem = f"{pf[1]:.0f} MB"
        else:
            cpu = mem = "—"
        items = [f'<li><span class="t">{lcb}</span><span>LCB 原始判分</span></li>',
                 f'<li><span class="t">{rej}</span><span>复核</span></li>']
        nums = [(f"{m['out'][q] / 1e3:.1f}k" if q in m["out"] else "—", "输出 token（含思考）"),
                (f"{m['lat'][q]:.0f} 秒" if q in m["lat"] else "—", "延迟"),
                (cpu, "最慢测试的 CPU 时间"), (mem, "峰值内存"),
                (str(st["sloc"]) if st else "—", "有效行"), (str(st["cc_total"]) if st else "—", "圈复杂度"),
                (f"{st['mi']:.1f}" if st else "—", "可维护性指数"), (str(st["pyflakes"]) if st else "—", "pyflakes 警告")]
        items += [f"<li><b>{v}</b><span>{lab}</span></li>" for v, lab in nums]
        cols.append(f"""<div class="model"><div>{dot(k)}<h3>{mname(name, short)}</h3></div>
<p class="verdict {c}">{t}</p><p class="cap">{status}</p><ul class="specs">{''.join(items)}</ul></div>""")
        code = r["code_list"][0]
        tabs.append(f'<button aria-pressed="{str(j == 0).lower()}" data-value="{CLS[k]}">{short}</button>')
        if code.strip():
            inner = (f'<div class="codehead"><span class="cap">{dot(k)} {name} · {len(code.splitlines())} 行</span>'
                     f'<button class="copy" data-src="code-{CLS[k]}">复制代码</button></div>'
                     f'<div id="code-{CLS[k]}">{highlight(code, PythonLexer(), HtmlFormatter(cssclass="code"))}</div>')
        else:
            inner = '<div class="empty">没有代码：API 返回的内容与题目无关。</div>'
        panels.append(f'<div data-panel-group="code" data-panel="{CLS[k]}"{"" if j == 0 else " hidden"}>{inner}</div>')
        data[k] = {"passed": m["passed"][q], "lcb_passed": m["lcb"][q], "mark": MARK.get(m["mark"].get(q), ""),
                   "failure": None if m["passed"][q] else m["why"][q], "lcb_failure": None if m["lcb"][q] else lcb_reason(r),
                   "rejudge": rej, "output_tokens": tokens_or_none(m, q), "latency_s": round(m["lat"][q], 1) if q in m["lat"] else None,
                   "cpu_s": round(pf[0], 4) if pf else None, "peak_mb": round(pf[1], 1) if pf else None,
                   "static": {x: st[x] for x in ("sloc", "comments", "cc_total", "mi", "depth", "pyflakes", "io")} if st else None,
                   "code": code}
    ex = f'<p><b>要点</b>：{EXAMPLE[q]}</p>' if q in EXAMPLE else ""
    prev_q, next_q = ORDER[i - 1] if i else None, ORDER[i + 1] if i + 1 < len(ORDER) else None
    pager = (f'<a href="{prev_q}.html">‹ {prev_q}</a>' if prev_q else "<span></span>") + \
            (f'<a href="{next_q}.html">{next_q} ›</a>' if next_q else "<span></span>")
    body = f"""<section class="section tight"><div class="wrap">
<p class="crumb"><a href="../problems.html">题目</a> › <span class="mono">{q}</span></p>
<h1 class="ptitle">{esc(title(p))}</h1>
<p class="meta">{contest(p)} · {p['contest_date'][:10]} · <span class="pill">{diff(p)}</span></p>
<p class="summary">{SUMMARY[q]}</p>
{ex}
<p><a class="btn" href="{url(p)}" target="_blank" rel="noopener">查看原题</a></p>
</div></section>
<section class="section alt"><div class="wrap">
<h2>结果</h2>
<div class="compare small" style="--rows:{3 + len(items)}">{''.join(cols)}</div>
<p class="note">CPU 时间与内存只统计能区分性能的题（最慢答案扣除进程启动后仍 ≥ {perfgen.THRESH:.1f} 秒），括号内为相对最快者的倍数（≥ 2 时标出）。静态指标只统计复核后通过的答案。</p>
</div></section>
<section class="section"><div class="wrap">
<div class="codehead"><h2>代码</h2><div class="seg" data-tabs="code">{''.join(tabs)}</div></div>
{''.join(panels)}
</div></section>
<div class="wrap"><nav class="pager">{pager}</nav></div>"""
    page(f"p/{q}.html", f"{q} {title(p)} · 代码能力评测", body, f"{q} {title(p)}：三个模型的结果与代码", "code.css")
    return {"id": q, "title": title(p), "platform": p["platform"], "difficulty": p["difficulty"], "contest": contest(p),
            "date": p["contest_date"][:10], "url": url(p), "summary": SUMMARY[q], "results": data}


def tokens_or_none(m, q):
    return m["out"].get(q)


# ---------------------------------------------------------------- results (结果)
def bar_chart():
    """LCB raw vs corrected passes per model."""
    W, top, bottom, left, right = 680, 34, 230, 34, 8
    span = bottom - top
    out = []
    for v in (0, 10, 20, 30):
        y = bottom - span * v / N
        out.append(f'<line class="grid" x1="{left}" x2="{W - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{v}</text>')
    gw, bw = (W - left - right) / len(MODELS), 56
    for i, (k, name, short) in enumerate(MODELS):
        cx = left + gw * (i + 0.5)
        for j, (v, faint) in enumerate(((S[k]["lcb"], True), (S[k]["pass"], False))):
            x = cx + (j - 1) * (bw + 6) + 3
            h = span * v / N
            out.append(f'<rect class="{CLS[k]}{" faint" if faint else ""}" x="{x:.1f}" y="{bottom - h:.1f}" width="{bw}" '
                       f'height="{h:.1f}" rx="5"/><text class="val" x="{x + bw / 2:.1f}" y="{bottom - h - 8:.1f}" '
                       f'text-anchor="middle">{v}</text>')
        out.append(f'<text class="cat" x="{cx:.1f}" y="{bottom + 24}" text-anchor="middle">{name}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {bottom + 36}" role="img" aria-label="LCB 原始判分与复核后的通过题数">'
            + "".join(out) + "</svg>"
            '<ul class="legend"><li><i class="faint"></i>LCB 原始判分</li><li><i></i>复核后</li></ul>')


def results():
    ms = [R[k] for k, *_ in MODELS]
    import collections
    dn = collections.Counter(P[q]["difficulty"] for q in P)
    pn = collections.Counter(P[q]["platform"] for q in P)

    def by(m, f):
        return sum(m["passed"][q] for q in P if f(P[q]))

    rows = [
        [("通过：LCB 原始判分", "")] + best_cells([sum(m["lcb"].values()) for m in ms], lambda v: f"{v}（{100 * v / N:.1f}%）", max),
        [("通过：复核后", "")] + best_cells([sum(m["passed"].values()) for m in ms], lambda v: f"{v}（{100 * v / N:.1f}%）", max),
        [(f"中等（{dn['medium']}）", "")] + best_cells([by(m, lambda p: p["difficulty"] == "medium") for m in ms], str, max),
        [(f"困难（{dn['hard']}）", "")] + best_cells([by(m, lambda p: p["difficulty"] == "hard") for m in ms], str, max),
        [(f"AtCoder（{pn['atcoder']}）", "")] + best_cells([by(m, lambda p: p["platform"] == "atcoder") for m in ms], str, max),
        [(f"LeetCode（{pn['leetcode']}）", "")] + best_cells([by(m, lambda p: p["platform"] == "leetcode") for m in ms], str, max),
        [("实际作答题数", "")] + [(str(len(m["by_q"])), "n") for m in ms],
        [("有效运行时间（分钟）", "")] + best_cells([m["wall"] for m in ms], lambda v: f"{v:.0f}", min),
        [("每题延迟中位数（秒）", "")] + best_cells([statistics.median(m["lat"].values()) for m in ms], lambda v: f"{v:.0f}", min),
        [("每题延迟 P90（秒）", "")] + best_cells([gen.pct(list(m["lat"].values()), 90) for m in ms], lambda v: f"{v:.0f}", min),
        [("每题延迟最长（秒）", "")] + best_cells([max(m["lat"].values()) for m in ms], lambda v: f"{v:.0f}", min),
        [("输出速度中位数（token/秒）", "")] + best_cells([S[k]["speed"] for k, *_ in MODELS], lambda v: f"{v:.0f}", max),
        [("输出 token 合计", "")] + [(ktok(m["tot"][2]), "n") for m in ms],
        [("其中思考 token 占比", "")] + [(f"{100 * m['tot'][3] / m['tot'][2]:.0f}%" if m["tot"][2] else "—", "n") for m in ms],
        [("每题输出 token 中位数", "")] + best_cells([statistics.median(m["out"].values()) for m in ms], ktok, min),
        [("输入 token 合计（缓存命中）", "")] + [(f"{ktok(m['tot'][0])}（{ktok(m['tot'][1])}）", "n") for m in ms],
        [("费用（美元，按 token 计）", "")] + best_cells([m["cost"] for m in ms], money, min),
        [("每道通过题的费用（美元）", "")] + best_cells([S[k]["per"] for k, *_ in MODELS], lambda v: money(v, 3), min),
        [("API 出错次数", "")] + [(str(len(m["errors"])), "n") for m in ms],
    ]
    drows = []
    for d, dname in (("medium", "中等"), ("hard", "困难")):
        qs = [q for q in P if P[q]["difficulty"] == d]
        for idx, ((k, name, short), m) in enumerate(zip(MODELS, ms)):
            have = [q for q in qs if q in m["out"]]
            row = [(dname if idx == 0 else "", ""), (f"{dot(k)} {name}", "nw"), (f"{sum(m['passed'][q] for q in qs)}/{len(qs)}", "n"),
                   (f"{statistics.median(m['lat'][q] for q in have):.0f}", "n"),
                   (ktok(statistics.mean(m["out"][q] for q in have)), "n"), (ktok(max(m["out"][q] for q in have)), "n")]
            drows.append((' class="grp"' if idx == 2 and d == "medium" else "", row))
    prow = []
    for q in ORDER:
        p = P[q]
        cells = [(f'<a class="mono" href="p/{q}.html">{q}</a>', "nw"), (esc(title(p)), ""), (diff(p), "nw")]
        for k, *_ in MODELS:
            m = R[k]
            c, t = verdict(k, q)
            why = "" if m["passed"][q] else f' <span class="sec">{m["why"][q]}</span>'
            cells += [(f'<span class="{c}">{t}</span>{why}', "nw"),
                      (f"{m['out'][q] / 1e3:.1f}k" if q in m["out"] else "—", "n"),
                      (f"{m['lat'][q]:.0f}" if q in m["lat"] else "—", "n")]
        prow.append(cells)
    phead = [("题号", ""), ("题目", ""), ("难度", "")]
    for k, name, short in MODELS:
        phead += [(f"{dot(k)} {short}", ""), ("token", "n"), ("秒", "n")]
    # performance
    perf_rows = []
    for q in perfgen.measurable:
        d = perfgen.prob[q]
        best = min(v[0] for v in d.values())
        cells = [(f'<a class="mono" href="p/{q}.html">{q}</a>', "nw"), (diff(P[q]), "nw"),
                 ("LC" if P[q]["platform"] == "leetcode" else "AC", "nw"), (f"{perfgen.sizes[q]['max_bytes'] / 1024:.0f}", "n")]
        for k, *_ in MODELS:
            if k not in d:
                cells += [("—", "n"), ("—", "n")]
                continue
            c = d[k][0]
            txt = f"{c:.2f}" + (f" <span class=\"sec\">{c / best:.1f}×</span>" if best > 0 and c / best >= 2 else "")
            cells += [(txt, "n best" if c == best else "n"), (f"{d[k][2] / 1024:.0f}", "n")]
        perf_rows.append(cells)
    pfhead = [("题号", ""), ("难度", ""), ("类型", ""), ("最大输入 KB", "n")]
    for k, name, short in MODELS:
        pfhead += [(f"{dot(k)} {short} CPU 秒", "n"), ("MB", "n")]
    agg = perfgen.agg
    gm_best = min(a[0] for a in agg.values())
    srows = [[(f"{dot(k)} {name}", "nw"), (f"{agg[k][0]:.2f}", "n best" if agg[k][0] == gm_best else "n"), (str(agg[k][1]), "n"),
              (str(agg[k][2]), "n"), (f"{agg[k][3]:.1f}", "n"), (f"{agg[k][4]:.0f}", "n"), (f"{agg[k][5]:.0f}", "n")]
             for k, name, short in MODELS]
    # static
    strows, iorows = [], []
    import collections as C
    for k, name, short in MODELS:
        Rr = [r for r in perfgen.static if r["model"] == k and r["q"] in perfgen.st_common]
        io = C.Counter(r["io"] for r in Rr if r["platform"] == "atcoder")
        strows.append([(f"{dot(k)} {name}", "nw"), (str(sum(r["sloc"] for r in Rr)), "n"),
                       (f"{statistics.median(r['sloc'] for r in Rr):.0f}", "n"), (str(sum(r["comments"] for r in Rr)), "n"),
                       (f"{statistics.median(r['cc_total'] for r in Rr):.0f}", "n"), (f"{statistics.median(r['mi'] for r in Rr):.1f}", "n"),
                       (f"{statistics.median(r['depth'] for r in Rr):.0f}", "n"), (str(sum(r["pyflakes"] for r in Rr)), "n")])
        iorows.append([(f"{dot(k)} {name}", "nw"), ("、".join(f"<code>{x}</code> {v}" for x, v in io.most_common()), "")])
    ncom = len(perfgen.common)
    body = f"""<section class="section tight"><div class="wrap">
<h2 id="overall">结果</h2>
<p class="sub">35 题，每题 1 次（pass@1）。粗体为该行最优；按难度、来源的通过数均为复核后结果。1 题 = 2.9 个百分点。</p>
{bar_chart()}
<h3>总表</h3>
{table([("指标", "")] + MHEAD, rows)}
<p class="note">有效运行时间 = 成功请求覆盖的时长（不含因余额不足暂停的时间）。延迟含服务端排队。API 出错：DS-V4-Pro 13 次为余额不足（402）；Kimi 30 次为挂起请求被切断后的连接错误，1 次为余额不足（429）。</p>
<h3>按难度</h3>
{table([("难度", ""), ("模型", ""), ("通过", "n"), ("延迟中位数（秒）", "n"), ("平均输出 token", "n"), ("最多输出 token", "n")], drows)}
<h3 id="matrix">逐题结果</h3>
{table(phead, prow)}
<p class="note">每个模型：结果（复核后）/ 输出 token（含思考）/ 延迟（秒）。✓* LCB 判为失败、复核后通过；✓† API 返回与题目无关的内容，人工另行调用验证正确，按通过计。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="perf">代码性能</h2>
<p class="sub">复核后通过的答案在绑定单核的全新进程里重跑官方测试，每个测试 3 次取中位数。只比较 {len(perfgen.measurable)} 道耗时足以区分的题。</p>
{table(pfhead, perf_rows)}
<p class="note">CPU 秒为最慢一个测试的 CPU 时间（扣除进程启动）；粗体为该题最快，灰字为相对最快者的倍数（≥ 2 时标出）。MB 为各测试中的最大峰值内存。AC = AtCoder，LC = LeetCode。</p>
<h3>汇总</h3>
{table([("模型", ""), ("相对最快倍数（几何平均）", "n"), ("最快（题）", "n"), ("慢 ≥ 2 倍（题）", "n"), ("CPU 合计（秒）", "n"), ("内存中位数 MB", "n"), ("内存最大 MB", "n")], srows)}
<p class="note">基于 {ncom} 道可比题（三个模型都通过）。“最快”按严格最小值计；有 3 题第二名与最快相差不到 5%（噪声范围内）：<code>3765</code>、<code>3801</code> 上 Flash 比 Kimi 慢 3% 和 2%，<code>abc399_c</code> 上 Kimi 比 Pro 慢 3%。按并列计，Flash 的最快题数为 2。</p>
<h3>差距最大的题</h3>
<ul class="list">
<li><a href="p/arc195_b.html"><code>arc195_b</code></a>（Flash 慢 8.5 倍，内存 91 MB）：Flash 枚举 A、B 所有不同取值的两两组合，复杂度 O(U·V)，并把重复的和逐个展开存入列表；Kimi 先按通配数量选出必须参与配对的候选值，再用二分查找限定候选和，0.15 秒。</li>
<li><a href="p/abc400_g.html"><code>abc400_g</code></a>（Pro 慢 9.3 倍）：Pro 为每组数据建图跑最小费用流；Kimi 用“取最大值后只修正奇偶”的贪心，每类只保留前两个候选，O(N log N)。</li>
<li><a href="p/3765.html"><code>3765</code></a>（Pro 慢 9.1 倍）：Pro 按子数组个数分层、每层做凸包优化，O(n² log n)；Kimi 直接用 O(n²) 的后缀 DP。</li>
<li><a href="p/3801.html"><code>3801</code></a>（Pro 慢 8.3 倍）：Pro 对每个可能的数位和 S 单独建 [剩余位数][和][积 mod S] 计数表；Kimi 用以（位置，和，积）为状态的记忆化数位 DP。</li>
<li><a href="p/abc397_g.html"><code>abc397_g</code></a>：Pro 0.23 秒、Kimi 0.01 秒，倍数大但绝对值都很小。</li>
<li>全部可比题的最慢测试都在 1.5 秒以内，未接近 AtCoder 常见的 2 秒时限；但评测机器与 AtCoder 不同，不能据此判断能否在原平台通过。</li>
</ul>
<h3 id="static">静态指标</h3>
{table([("模型", ""), ("有效行合计", "n"), ("有效行中位数", "n"), ("注释行合计", "n"), ("圈复杂度中位数", "n"), ("可维护性中位数", "n"), ("嵌套深度中位数", "n"), ("pyflakes 警告", "n")], strows)}
{table([("模型", ""), ("AtCoder 读入方式（题数）", "")], iorows)}
<p class="note">基于 {len(perfgen.st_common)} 道三个模型都通过的题。有效行不含空行和注释；圈复杂度为每份答案所有函数之和（radon）；可维护性指数 0–100，越高越好（radon）；pyflakes 警告全部为“局部变量赋值后未使用”。不评价可读性、命名等主观项。Kimi 采样温度 1.0、DeepSeek 0.2，风格差异部分来自采样。</p>
<ul class="list">
<li>Kimi：可比题上整体最快（几何平均 {agg[KF][0]:.2f} 倍），代码最短、注释最多、无 pyflakes 警告；读入几乎都用一次性 <code>sys.stdin.buffer.read()</code>。</li>
<li>DS-V4.1-Flash：没有一题严格最快（2 题与最快并列），{agg[FL][2]} 题慢 2 倍以上；最差情况为 <code>arc195_b</code> 的平方复杂度枚举。</li>
<li>DS-V4-Pro：两极分化，{agg[PR][1]} 题最快，也有 {agg[PR][2]} 题慢 2 倍以上（4 题 8 倍以上），倾向用更通用、更重的算法；代码最长、圈复杂度最高，4 个未使用变量。</li>
</ul>
</div></section>
<section class="section"><div class="wrap">
<h2 id="cost">费用核对</h2>
<p class="sub">按官方单价 × token 计算，再用账户余额变化核对。</p>
<ul class="list">
<li>DS-V4.1-Flash：账户余额 ¥11.32 → ¥9.37，实扣 ¥1.95；按美元价目折算为 {money(R[FL]['cost'])}（人民币账户按人民币价目扣费）。</li>
<li>DS-V4-Pro：按 token 计 {money(R[PR]['cost'])}（全部在谷时）。运行期间两次充值的金额未记录，无法用余额核对。13 次调用因余额不足立即返回 402，不生成内容，充值后补跑。</li>
<li>Kimi K3.1 Pro：三次充值共 $17.50，最终余额 −$0.09，实扣 $17.59。成功返回的 35 次调用按 token 计 {money(R[KF]['cost'])}。差额 $9.02（由余额变化推算）对应 7 个未返回结果的请求：4 个在余额耗尽后挂起 1–1.5 小时，3 个被手动中断。</li>
</ul>
<h3>分析</h3>
<ul class="list">
<li>复核后唯一的真实错误：Kimi <a href="p/abc398_g.html"><code>abc398_g</code></a>（博弈题），思考 11.9 万 token、耗时 31 分钟后，在 4/43 个测试上答案错误。这题 DS-V4.1-Flash 用 6.3 万 token、DS-V4-Pro 用 17.4 万 token 都做对了。</li>
<li>推理量：每题输出 token 中位数 DS-V4.1-Flash 12k、Kimi 14k、DS-V4-Pro 38k；困难题平均分别为 22k、31k、61k。DS-V4-Pro 多用的 token 没有换来更多通过题。</li>
<li>调用稳定性：DeepSeek 余额不足时立即返回 402，补跑即可，已答结果不丢。Kimi 非流式请求在余额耗尽后挂起 1–1.5 小时，既不返回也不报错；改为流式 + 5 分钟空闲超时后，最后 3 题单路完成（每题 20–31 分钟）。</li>
<li>LCB 原始判分的误差：在这 35 题上，原始判分把 Flash 和 Pro 都低估了，Flash 少算 5 题、Pro 少算 3 题，而且两者的排序也被颠倒（原始 Pro 领先 2 题，复核后持平）。凡是用 LCB 判分做模型对比，都应复核失败题。</li>
</ul>
<h3>局限</h3>
<ul class="list">
<li>35 题、每题 1 次：相差 1–2 题不显著；两个 DeepSeek 模型均为满分，这批题已不足以区分二者。</li>
<li>采样温度不同：DeepSeek 0.2，Kimi 固定 1.0。</li>
<li>延迟受并发和服务端负载影响。</li>
<li>题目早于三个模型发布，不排除训练数据污染。</li>
<li>复核后的成绩依赖本评测的重判程序和校验器；LCB 原始判分同时列出，可对照。</li>
<li>Kimi <code>abc399_e</code> 按人工另行调用的结果计为通过，未在本评测流程中复现。</li>
</ul>
</div></section>"""
    page("results.html", "结果 · 代码能力评测", body, "通过率、延迟、token、费用、代码性能与静态指标")


# ---------------------------------------------------------------- method (原理)
def method():
    models_tbl = table([("", "")] + [(f"{dot(k)} {name}", "") for k, name, short in MODELS], [
        [("API 模型名", "nw"), ("<code>kimi-k3.1-pro</code>", ""), ("<code>deepseek-flash</code>", ""), ("<code>deepseek-v4-pro</code>", "")],
        [("最近更新", "nw"), ("K3.1 系列首发", ""), ("2026-10-17（1017 版）", ""), ("2026-08-13（GA）", "")],
        [("规模", "nw"), ("3T 级，K3（2.8T）后训练", ""), ("552B MoE，激活 8B 输入 / 16B 输出", ""), ("未公布", "")],
        [("权重", "nw"), ("开放", ""), ("开放，MIT", ""), ("—", "")],
        [("上下文 / 最大输出", "nw"), ("1M / 默认 131,072", ""), ("1M / 393,216", ""), ("1M / 393,216", "")],
        [("输入", "nw"), ("文本、图像", ""), ("文本、图像", ""), ("文本", "")],
        [("思考档位", "nw"), ("恒开；low/high/max，默认 max", ""), ("low/high/max，默认 high", ""), ("low/high/max，默认 high", "")],
        [("采样", "nw"), ("固定 T=1.0、top_p=0.95", ""), ("推荐 T=1.0", ""), ("—", "")],
        [("单价（美元/百万 token：输入 / 缓存 / 输出）", ""), ("2 / 0.2 / 10，无峰谷", ""), ("0.3 / 0.006 / 1.2，谷时半价", ""),
         ("1.32 / 0.044 / 3.96，谷时半价", "")],
    ])
    setting = table([("项目", ""), ("设置", "")], [
        [("评测集", "nw"), ("LiveCodeBench release_v6（ICLR 2025），官方提示词、官方判题，隐藏测试全过才算通过", "")],
        [("指标", "nw"), ("pass@1，每题 1 次", "")],
        [("调用", "nw"), ("各厂商官方 API；codingBench 的 <code>cb livecodebench</code>", "")],
        [("思考档位", "nw"), ("各模型默认（Kimi max，DeepSeek high）", "")],
        [("采样", "nw"), ("DeepSeek：temperature 0.2（LCB 官方）；Kimi：固定 1.0（API 不允许传入）", "")],
        [("输出上限", "nw"), ("DeepSeek 262,144；Kimi 131,072（默认）；全部回答正常结束（finish_reason=stop），无截断", "")],
        [("并发", "nw"), ("V4.1-Flash 16，V4-Pro 8；Kimi 前 32 题 4 路非流式，后 3 题 1 路流式（5 分钟无 token 判超时）", "")],
        [("计量", "nw"), ("每次调用记录起止时间与服务端返回的 token 数（含思考）", "")],
        [("费用", "nw"), ("官方单价 × token，DeepSeek 按调用时段区分峰谷；用账户余额变化核对", "")],
    ])
    issues = table([("问题", ""), ("受影响答案", ""), ("LCB 判定", "nw"), ("复核", "")], [
        [("测试数据错误：<code>abc397_d</code> 第 41 个测试 N=27，标准答案为“3 0”；y=0 不是正整数，27 不存在正整数解，正确输出为 -1", ""),
         ("三个模型（均输出 -1）", ""), ("答案错误", "nw"), ("校验器 43/43", "nw")],
        [("多解题按单一答案比对：<code>arc195_c</code> 允许任意合法构造", ""), ("三个模型", ""), ("答案错误", "nw"), ("校验器 5/5", "nw")],
        [("<code>sys.stdin.buffer.readline</code> 模拟错误：每次都返回输入的第一行", ""),
         ("Flash <code>abc399_c</code>、<code>arc196_b</code>；Pro <code>arc196_b</code>", ""), ("答案错误 / 运行错误", ""), ("真实输入全部通过", "")],
        [("不支持 <code>sys.stdout.buffer</code>：标准输出被替换为 StringIO", ""), ("Kimi、Flash <code>abc398_f</code>", ""),
         ("运行错误", "nw"), ("真实输出 43/43", "nw")],
        [("API 返回与题目无关的内容（一部电影的营销手法）", ""), ("Kimi <code>abc399_e</code>", ""), ("无代码", "nw"),
         ("人工另行调用，验证正确", "")],
    ])
    perf_tbl = table([("项目", ""), ("设置", "")], [
        [("对象", "nw"), (f"复核后通过的答案（Kimi {sum(r['model'] == KF for r in perfgen.static)} 份，不含 <code>abc398_g</code>、<code>abc399_e</code>；DeepSeek 各 {N} 份）", "")],
        [("运行", "nw"), (f"每次运行都是一个全新的 Python 3.11 进程（LCB 环境），绑定到单个 CPU 核；共 {sum(1 for r in perfgen.rows if r['model'] != 'baseline'):,} 次，输出全部正确", "")],
        [("计时", "nw"), (f"AtCoder：进程 CPU 时间（rusage）扣除启动基线 {1000 * perfgen.B:.1f} ms；LeetCode：只计 <code>Solution</code> 方法调用的 CPU 时间", "")],
        [("内存", "nw"), (f"进程峰值常驻内存（ru_maxrss）；空程序为 {perfgen.base_rss / 1024:.1f} MB", "")],
        [("重复", "nw"), (f"每个测试 3 次、三个模型轮流先跑，取中位数；同一测试 3 次的离散度中位数 "
                          f"{100 * statistics.median(perfgen.spread):.1f}%，P90 {100 * sorted(perfgen.spread)[int(0.9 * (len(perfgen.spread) - 1))]:.1f}%", "")],
        [("可比题", "nw"), (f"最慢答案扣除启动后仍 ≥ {perfgen.THRESH:.1f} 秒的题，共 {len(perfgen.measurable)} 题；其余 {len(perfgen.small)} 题官方测试太小，耗时主要是启动开销，不比较", "")],
    ])
    body = f"""<section class="section tight"><div class="wrap">
<h2>原理</h2>
<p class="sub">用 LiveCodeBench 的官方题目、提示词和判题程序评测，再对判为失败的答案复核，最后测量通过答案的运行效率和代码指标。</p>
<div class="steps">
<div class="card"><h4>选题</h4><p>release_v6 最新 100 题中取最新的中等 10、困难 25 题。</p></div>
<div class="card"><h4>生成</h4><p>官方提示词，每题调用模型 API 1 次，提取回答中的最后一个代码块。</p></div>
<div class="card"><h4>判题</h4><p>AtCoder 题作为完整程序读写标准输入输出，LeetCode 题调用给定函数；隐藏测试全过才算通过。</p></div>
<div class="card"><h4>复核</h4><p>用真实 stdin/stdout 重跑全部 AtCoder 答案，多解题用校验器。</p></div>
<div class="card"><h4>代码分析</h4><p>通过的答案绑核重跑，测 CPU 时间与峰值内存；radon、pyflakes 统计代码指标。</p></div>
</div>
<h3>评测设置</h3>
{setting}
<h3>为什么用最新的题</h3>
<p>LiveCodeBench 持续从 AtCoder、LeetCode、Codeforces 收集比赛题并标注发布日期，可以只用某个日期之后的题，降低训练数据污染。本次 35 题发布于 2025-03-15 至 2025-04-06，仍早于三个模型的发布时间，不排除污染（见“结果 › 局限”）。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="rejudge">判分与复核</h2>
<p class="sub">LCB 判题程序在标准输入输出上有缺陷，测试数据也有错误。只用原始判分会低估模型，甚至颠倒排名。</p>
{issues}
<p class="note">复核方法：26 道 AtCoder 题 × 3 个模型 = 78 份答案，作为独立 Python 进程用真实 stdin/stdout 运行官方全部测试（每个测试 6 秒）。两道多解题用按题意编写的校验器，其余逐 token 比对。LCB 判为通过的答案复核后全部仍通过。LeetCode 9 题为函数调用，不受上述问题影响，沿用 LCB 判分。上述问题均出自 LCB 官方判题代码与数据（本评测固定的版本），未作修改。Kimi <code>abc398_g</code> 在 LCB 中报 IndexError，也是 readline 问题导致；换成真实输入后仍有 4/43 个测试答案错误，按失败计。</p>
</div></section>
<section class="section"><div class="wrap">
<h2 id="perf">性能测量</h2>
<p class="sub">只比较复核后通过的答案，所有输出都校验正确后才计入。</p>
{perf_tbl}
<h3 id="static">静态指标</h3>
<ul class="list">
<li>有效行：不含空行和注释的代码行（radon raw）。注释行含文档字符串。</li>
<li>圈复杂度：每份答案所有函数与方法的圈复杂度之和（radon cc）。</li>
<li>可维护性指数：0–100，越高越好（radon mi，含多行字符串）。</li>
<li>嵌套深度：语法树中复合语句（if、for、while、with、try、def、class、match）的最大嵌套层数。</li>
<li>pyflakes 警告：未使用的变量、未定义的名字等。</li>
</ul>
<p>这些指标只描述代码形态，不评价可读性、命名等主观项。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2>参评模型</h2>
<p class="sub">信息取自两家官方文档与 API <code>/v1/models</code>（{DATE}）。</p>
{models_tbl}
<h3>Kimi K3.1 Pro</h3>
<ul class="list">
<li>变更：在 K3 上大幅增加后训练算力，覆盖数百个领域联合 RL；重做 RL 框架、长上下文推理、沙箱、rollout 调度。</li>
<li>官方提升方向：编程、3D 建模（直接写 Blender / CAD 脚本）、金融研究（内部 Financial Research 比 K3 高 11.6 分）、智能体。</li>
<li>安全：中期训练与 RL 数据剔除网络安全内容；xdev-bench-hard pass@3 81.0%（不剔除 90.5%）。</li>
<li>高速版 <code>kimi-k3.1-pro-highspeed</code>：速度 2–3 倍，价格 2 倍。K2 系列 2026 年底下线。</li>
<li>使用限制：充值 ≥ 1 美元解锁；累计充值决定并发 / TPM；temperature、top_p、n、penalty 不可传。</li>
<li>官方文档中的编程基准分数为占位符（“[xx.x%]”），无可引用数据。</li>
</ul>
<h3>DeepSeek-V4.1-Flash</h3>
<ul class="list">
<li>2026-09-10 发布：20 层因果编码器 + 20 层解码器；MoE 1 共享 + 384 路由专家，每 token 激活 6 个；KV 缓存 890 字节/token，HBM 为上一代 1/4、SSD 为 1/8；原生视觉；降价；V4-Flash 下线。</li>
<li>2026-10-17 更新为 1017 版（新 / 旧）：Terminal-Bench 4.0 42.3 / 31.2，DeepSWE v1.1 77.0 / 74.2，ProgramBench 29.1 / 20.3，NL2Repo 68.2 / 65.4，HLE 42.6 / 36.8；输出更短、耗时更少；价格与调用方式不变。</li>
<li>Codeforces 3471（max 档；同表 V4-Pro 3348）。输出单价为 V4-Pro 的 30%、Kimi K3.1 Pro 的 12%。</li>
</ul>
<h3>DeepSeek-V4-Pro</h3>
<ul class="list">
<li>2026-04-24 首发；2026-08-13 GA：HLE 42.7 / 60.0（无 / 有工具），Terminal-Bench 2.1 87.9，DeepSWE 62.7，NL2Repo 61.5，Toolathlon-Verified 74.1；引入 low/high/max 三档；2026-08-16 起峰谷定价。</li>
<li>V4.1-Flash 新闻稿称 9 月 14 日起该模型名改由 V4.1-Flash 承接，更新日志称继续提供、计费不变。本次 API 返回的模型名为 <code>deepseek-v4-pro</code>，按 V4-Pro 单价扣费。</li>
<li>仅文本输入；单价为 V4.1-Flash 的 3.3 倍；DeepSeek 自报多数基准低于 V4.1-Flash。</li>
</ul>
</div></section>
<section class="section"><div class="wrap">
<h2>来源</h2>
<ul class="list">
<li>LiveCodeBench：<a href="https://livecodebench.github.io">livecodebench.github.io</a></li>
<li>Kimi：<a href="https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart">K3.1 Pro 快速开始</a>、<a href="https://platform.kimi.ai/docs/models">模型列表</a>、<a href="https://platform.kimi.ai/docs/pricing/chat">价格</a></li>
<li>DeepSeek：<a href="https://api-docs.deepseek.com/updates/">更新日志</a>、<a href="https://www.deepseek.com/en/news/deepseek-v4-1-flash/">V4.1-Flash 发布</a>、<a href="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash">模型卡</a>、<a href="https://api-docs.deepseek.com/quick_start/pricing">价格</a></li>
<li>上下文、最大输出、默认档位：两家 API <code>/v1/models</code>（{DATE}）</li>
</ul>
</div></section>"""
    page("method.html", "原理 · 代码能力评测", body, "评测流程、设置、LCB 判分问题与复核、性能测量方法、参评模型")


def assets():
    a = os.path.join(OUT, "assets")
    os.makedirs(a, exist_ok=True)
    for f in ("style.css", "app.js"):
        shutil.copy(os.path.join(HERE, "site_assets", f), a)
    light = [x for x in HtmlFormatter(style="xcode").get_style_defs(".code").splitlines() if x.startswith(".code .")]
    dark = [x for x in HtmlFormatter(style="github-dark").get_style_defs(".code").splitlines() if x.startswith(".code .")]
    open(os.path.join(a, "code.css"), "w").write(
        "/* Pygments: xcode (light), github-dark (dark) */\n" + "\n".join(light)
        + "\n@media (prefers-color-scheme: dark) {\n" + "\n".join("  " + x for x in dark) + "\n}\n")
    open(os.path.join(a, "icon.svg"), "w").write(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#1d1d1f"/>'
        '<path d="M12 10l-6 6 6 6M20 10l6 6-6 6" fill="none" stroke="#f5f5f7" stroke-width="2.6" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>')


def main():
    for d in ("p", "assets", "data"):
        shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
    assets()
    index()
    problems()
    method()
    results()
    probs = [problem_page(i, q) for i, q in enumerate(ORDER)]
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    data = {
        "date": DATE,
        "benchmark": "LiveCodeBench release_v6, newest 35 problems (10 medium, 25 hard), pass@1, n=1",
        "verdicts": "passed = after re-judge (real stdin/stdout, checkers for abc397_d and arc195_c); lcb_passed = LCB's own judge",
        "models": [{"id": k, "name": name, "passed": S[k]["pass"], "lcb_passed": S[k]["lcb"],
                    "median_latency_s": round(S[k]["lat"], 1), "median_output_tokens_per_s": round(S[k]["speed"], 1),
                    "cost_usd": round(S[k]["cost"], 4), "perf_geomean_vs_fastest": round(S[k]["gm"], 3)} for k, name, _ in MODELS],
        "problems": probs,
    }
    json.dump(data, open(os.path.join(OUT, "data", "lcb35.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("pages:", 4 + len(probs), "->", OUT)


if __name__ == "__main__":
    main()
