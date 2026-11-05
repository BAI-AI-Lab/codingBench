"""Build the public results site (GitHub Pages, BAI-AI-Lab/coding-eval) of this report: python site.py <out dir>.

Every number comes from analysis.json and paper_data.json, the files main.pdf is built from. The problem pages also
read data/dirs/<run>/{answers,judge,perf,complexity,quality}.jsonl for the code and the per-sample detail. data/ holds
the statements and never leaves the evaluation machine: the site carries titles, one-line summaries
(problem_summaries.json, written from the statements), official links, scores, usage and the models' code.
Output is plain HTML with relative links, Pygments-highlighted code, inline SVG and no external resources (CDNs are
unreliable from China). <out dir>/archive/ (earlier evaluations) is left untouched. Needs pygments.
"""
import collections
import html
import json
import math
import os
import re
import shutil
import statistics
import sys

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import CppLexer, PythonLexer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(sys.argv[1])
DATE = "2026-11-03"
REPORT = "report-2026-11-03.pdf"  # main.pdf of this directory
ARCHIVE = "archive/2026-10-23/index.html"  # the LiveCodeBench newest-35 evaluation, kept as it was published

A = json.load(open(os.path.join(HERE, "analysis.json")))
D = json.load(open(os.path.join(HERE, "paper_data.json")))
META = json.load(open(os.path.join(HERE, "data", "dirs", "meta.json")))["meta"]
SUMMARY = json.load(open(os.path.join(HERE, "problem_summaries.json")))
esc = html.escape

KIMI, HIGH, DS, MM = "kimi-k3.1-pro", "kimi-k3.1-pro-high", "deepseek-flash", "MiniMax-M3.1-Flash"
MAIN = [KIMI, DS, MM]
ALL = [KIMI, HIGH, DS, MM]
RUN = {KIMI: "kimi", HIGH: "kimi_high", DS: "deepseek", MM: "minimax"}
CLS = {KIMI: "kimi", HIGH: "kimih", DS: "ds", MM: "mm"}
NAME = {KIMI: "Kimi K3.1 Pro", HIGH: "Kimi K3.1 Pro（high）", DS: "DeepSeek Flash V4.1-1017", MM: "MiniMax M3.1 Flash"}
SHORT = {KIMI: "Kimi", HIGH: "Kimi high", DS: "DeepSeek", MM: "MiniMax"}
API = {KIMI: "kimi-k3.1-pro", HIGH: "kimi-k3.1-pro", DS: "deepseek-flash", MM: "MiniMax-M3.1-Flash"}
TIERS = ["L1", "L2", "L3", "L4", "L5"]
TN = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式", "L1-L4": "L1–L4 合计", "all": "合计"}
GROUP = {"L1": "铜组", "L2": "银组", "L3": "金组", "L4": "铂金组"}
EGOI_DAY = {"biscuits": "day1", "ferriswheel": "day1", "ovenmasters": "day1", "cakes": "day2", "foxfamilies": "day2",
            "wateringplants": "day2"}
EGOI_SHA, FCS_SHA = "08eedd32c99edf2223ea3987744898f7b774cb47", "12ab26840cff15f1d0ab09004dafd07f92c14b60"
FAIL = [("no code", "无代码"), ("timeout", "生成超时"), ("CE", "编译错误"), ("WA", "答案错误"), ("RE", "运行错误"),
        ("TLE", "超时"), ("partial", "部分分")]
FAILN = dict(FAIL) | {"MLE": "超内存", "JE": "判题错误"}
CPLX = [("better", "更优"), ("same", "同阶"), ("worse", "更差"), ("uncertain", "不确定"), ("not measurable", "不可测")]
CPLXN = dict(CPLX) | {"no reference": "无官方解"}
UP, DN = " ↑", " ↓"
LEGEND = "↑ 越大越好，↓ 越小越好"
U, E, AGG, SAMP = A["usage"], A["effort"], D["agg"], D["samples"]


def jl(p):
    return [json.loads(x) for x in open(p) if x.strip()] if os.path.exists(p) else []


def load(name):
    return {m: {r["q"]: r for r in jl(os.path.join(HERE, "data", "dirs", RUN[m], name))} for m in ALL}


ANS, JUDGE, PERF, CPLXR, QUAL = load("answers.jsonl"), load("judge.jsonl"), load("perf.jsonl"), load("complexity.jsonl"), load("quality.jsonl")
for m in ALL:
    assert set(ANS[m]) == set(SAMP[m]), m
ORDER = [p for t in TIERS for p in D["tiers"][t]]
assert set(ORDER) == set(META) == set(SUMMARY) and len(ORDER) == 112


def models_in(t):
    return [KIMI] + ([HIGH] if t in ("L4", "L5") else []) + [DS, MM]


def samples(m, pid):
    """The samples of model m on a problem, in order (#0, #1, ...)."""
    return sorted((q for q in SAMP[m] if SAMP[m][q]["pid"] == pid), key=lambda q: int(q.split("#")[1]))


def f(x, nd=1):
    return "—" if x is None else f"{x:.{nd}f}"


def neg(s):
    return s.replace("-", "−")


def ci(c, nd=1):
    return neg(f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]")


def sg(x, nd=1):
    return neg(f"{x:+.{nd}f}")


def sig(c):
    return c[0] > 0 or c[1] < 0


def pv(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def usd(v, nd=2):
    return "—" if v is None else f"${v:.{nd}f}"


def ktok(v):
    return f"{v / 1000:.1f}k"


def dot(m):
    return f'<span class="dot {CLS[m]}"></span>'


def mname(m):
    return f'<span class="long">{NAME[m]}</span><span class="short">{SHORT[m]}</span>'


def effort(m, t):
    if m == HIGH:
        return "high"
    if m == KIMI:
        return "auto（max）" if t in ("L1", "L2", "L3") else "max"
    return {DS: "auto（high）", MM: "auto（max）"}[m]


# ---------------------------------------------------------------- problems
def url(pid):
    kind, rest = pid.split("-", 1)
    if kind == "usaco":
        return f"https://usaco.org/index.php?page=viewproblem2&cpid={rest}"
    if kind == "egoi26":
        return f"https://github.com/egoi-org/egoi-2026/tree/{EGOI_SHA}/{EGOI_DAY[rest]}/{rest}"
    return f"https://github.com/FrontierCS/Frontier-CS/tree/{FCS_SHA}/algorithmic/problems/{rest}"


def source(pid):
    m = META[pid]
    if m["source"] == "usaco":
        return f"USACO {GROUP[m['tier']]}"
    return "EGOI 2026" if m["source"] == "egoi2026" else "FrontierCS"


def contest(pid):
    m = META[pid]
    if m["source"] == "usaco":
        c = re.match(r"USACO (\d{4}) (.+?) Contest, (\w+)", m["contest"])
        return f"USACO {c.group(1)} {c.group(2)} · {GROUP[m['tier']]}" if c else m["contest"]
    return "EGOI 2026" if m["source"] == "egoi2026" else "FrontierCS 算法赛道 v1.1"


def title(pid):
    t = META[pid]["title"]
    if META[pid]["source"] == "egoi2026":
        return re.sub(r"^[A-Z]\. ", "", t)
    if META[pid]["source"] == "frontiercs":
        return f"FrontierCS 第 {pid.split('-')[1]} 题"
    return t


LANG = {"python": "Python 3.11", "cpp": "C++17"}
SCORING = {"tests": "测试点等分", "groupmin": "子任务取最低分", "mean": "0–100 连续分"}


def time_limit(pid):
    for m in ALL:
        for q in samples(m, pid):
            tl = {x.get("tl") for x in JUDGE[m][q].get("tests") or [] if x.get("tl")}
            if tl:
                return max(tl)
    return None


# ---------------------------------------------------------------- references (refs.bib, plus the agent section)
def bib():
    src = open(os.path.join(HERE, "refs.bib")).read()
    out = {}
    for typ, key, body in re.findall(r"@(\w+)\{(\w+),(.*?)\n\}", src, re.S):
        fl = {k.lower(): v for k, v in re.findall(r"(\w+)\s*=\s*\{(.*?)\}\s*(?:,|$)", body, re.S)}

        def clean(s):
            s = s.replace("{\\'e}", "é").replace("--", "–").replace("\\&", "&")
            s = re.sub(r"\\url\{([^}]*)\}", r"\1", s)
            return re.sub(r"[{}]", "", s).strip()

        names = [clean(a) for a in re.split(r"\s+and\s+", fl.get("author", ""))]
        names = [" ".join(reversed([x.strip() for x in n.split(",", 1)])) if "," in n else n for n in names]
        authors = ", ".join(names[:3]) + (", et al." if len(names) > 3 else "")
        venue = ""
        if "journal" in fl:
            venue = f"{clean(fl['journal'])}, {fl.get('volume', '')}({fl.get('number', '')}):{clean(fl.get('pages', ''))}"
        elif "eprint" in fl:
            venue = f"arXiv:{fl['eprint']}"
        note = clean(fl.get("note", ""))
        link = fl.get("url") or (re.search(r"\\url\{([^}]*)\}", fl.get("howpublished", "")) or [None, None])[1] \
            or (f"https://doi.org/{fl['doi']}" if "doi" in fl else None) \
            or (f"https://arxiv.org/abs/{fl['eprint']}" if "eprint" in fl else None)
        ttl = clean(fl.get("title", ""))
        text = f"{authors.rstrip('.')}. {ttl}{'' if ttl[-1:] in '?!.' else '.'}" + (f" {venue}," if venue else "") \
            + f" {fl.get('year', '')}." + (f" {note}。" if note else "")
        out[key] = (text, link)
    return out


BIB = bib()
AGENT_REFS = {
    "sweagent": ("John Yang, Carlos E. Jimenez, Alexander Wettig, et al. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024.", "https://arxiv.org/abs/2405.15793"),
    "effi": ("Zhiyu Fan, Kirill Vasilevski, Dayi Lin, et al. SWE-Effi: Re-Evaluating Software AI Agent System Effectiveness Under Resource Constraints. arXiv:2509.09853, 2025.", "https://arxiv.org/abs/2509.09853"),
    "verified": ("OpenAI. Introducing SWE-bench Verified. 2024-08-13.", "https://openai.com/index/introducing-swe-bench-verified/"),
    "tbench": ("Mike A. Merrill, et al. Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces. arXiv:2601.11868, 2026.", "https://arxiv.org/abs/2601.11868"),
    "impossible": ("Ziqian Zhong, Aditi Raghunathan, Nicholas Carlini. ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases. ICLR 2026.", "https://arxiv.org/abs/2510.20270"),
    "utboost": ("Boxi Yu, Yuxuan Zhu, Pinjia He, Daniel Kang. UTBoost: Rigorous Evaluation of Coding Agents on SWE-Bench. ACL 2025.", "https://arxiv.org/abs/2506.09289"),
    "wang": ("You Wang, Michael Pradel, Zhongxin Liu. Are \"Solved Issues\" in SWE-bench Really Solved Correctly? An Empirical Study. ICSE 2026.", "https://arxiv.org/abs/2503.15223"),
    "illusion": ("Shanchao Liang, Spandan Garg, Roshanak Zilouchian Moghaddam. The SWE-Bench Illusion: When State-of-the-Art LLMs Remember Instead of Reason. ICSE 2026 (SEIP).", "https://arxiv.org/abs/2506.12286"),
    "matter": ("Sayash Kapoor, Benedikt Stroebl, Zachary S. Siegel, et al. AI Agents That Matter. TMLR 2025.", "https://arxiv.org/abs/2407.01502"),
    "hal": ("Sayash Kapoor, Benedikt Stroebl, Peter Kirgis, et al. Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation. arXiv:2510.11977, 2025.", "https://arxiv.org/abs/2510.11977"),
}
REF_ORDER = []  # numbered in order of first citation on the method page


def cite(*keys, page=""):
    for k in keys:
        assert k in BIB or k in AGENT_REFS, k
        if k not in REF_ORDER:
            REF_ORDER.append(k)
    return '<span class="cite">[' + ", ".join(
        f'<a href="{page}#ref-{REF_ORDER.index(k) + 1}">{REF_ORDER.index(k) + 1}</a>' for k in keys) + "]</span>"


# ---------------------------------------------------------------- page frame
NAV = [("index.html", "概览"), ("problems.html", "题目"), ("method.html", "原理"), ("results.html", "结果"),
       ("custom.html", "自定义评测"), (REPORT, "报告")]


def page(path, title_, body, desc, extra_css=""):
    up = "../" * path.count("/")
    cur = ' aria-current="page"'
    links = "".join(f'<li><a href="{up}{h}"{cur if h == path else ""}>{t}</a></li>' for h, t in NAV)
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
<nav class="nav"><div class="nav-in"><a class="brand" href="{up}index.html"><span class="hide-sm">BAI AI Lab </span>代码评测</a><ul>{links}</ul></div></nav>
<main>
{body}
</main>
<footer><div class="wrap">
<p>BAI AI Lab 代码能力阶梯评测 · 数据截至 {DATE}</p>
<p>题目来自 USACO、EGOI 2026 与 FrontierCS，题面与测试数据的版权归原作者，本站只给出概述与原题链接；运行与判分用 <a href="https://github.com/BAI-AI-Lab/codingBench">codingBench</a>。</p>
<p>全部数据：<a href="{up}data/ladder.json">data/ladder.json</a> · 上一版评测：<a href="{up}{ARCHIVE}">LiveCodeBench 最新 35 题（2026-10-23）</a></p>
<p>如有任何问题，联系 <a href="https://alberthx86.github.io/" target="_blank" rel="noopener">Albert Huang</a>。</p>
</div></footer>
<script src="{up}assets/app.js"></script>
</body>
</html>
"""
    dst = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write(doc)


def table(head, rows, tid=None, cls=None):
    """head: [(html, css)]; rows: lists of (html, css), or (tr attributes, list)."""
    th = "".join(f'<th class="{c}">{t}</th>' if c else f"<th>{t}</th>" for t, c in head)
    trs = []
    for row in rows:
        attrs = ""
        if isinstance(row, tuple):
            attrs, row = row
        trs.append(f"<tr{attrs}>" + "".join(f'<td class="{c}">{t}</td>' if c else f"<td>{t}</td>" for t, c in row) + "</tr>")
    idattr = f' id="{tid}"' if tid else ""
    clsattr = f' class="{cls}"' if cls else ""
    return f'<div class="tw"><table{idattr}{clsattr}><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def tiered(groups):
    """[(tier label, [row cells])] -> rows with the tier label on the first row and a stronger rule after each tier."""
    rows = []
    for label, rr in groups:
        for i, r in enumerate(rr):
            rows.append((' class="grp"' if i == len(rr) - 1 else "", [(label if i == 0 else "", "nw")] + r))
    return rows


def mcell(m):
    return (f"{dot(m)} {SHORT[m]}", "nw")


def bold(v, best, txt):
    return (txt, "n best") if best is not None and v is not None and abs(v - best) < 1e-9 else (txt, "n")


def specs(items):
    return '<ul class="specs">' + "".join(f"<li><b>{v}</b><span>{lab}</span></li>" for v, lab in items) + "</ul>"


# ---------------------------------------------------------------- facts used in several places
M = A["metrics"]
P = A["pairs"]


def pair(a, b, t):
    return P[f"{a}|{b}"][t]


L14 = {m: M[m]["L1-L4"]["pass1"] for m in MAIN}
L4P = {m: M[m]["L4"]["pass1"] for m in [KIMI, HIGH, DS, MM]}
L5S = {m: M[m]["L5"]["score"] for m in [KIMI, HIGH, DS, MM]}
assert L14[KIMI] > L14[DS] > L14[MM] and all(sig(pair(a, b, "L1-L4")["ci"]) for a, b in ((KIMI, DS), (KIMI, MM), (DS, MM)))
assert L4P[KIMI] > L4P[DS] > L4P[HIGH] > L4P[MM] and L5S[KIMI] > L5S[HIGH] > L5S[DS] > L5S[MM]
REF_L5 = 60  # FrontierCS: the official reference solution scores 60
assert max(L5S.values()) < REF_L5
TPS = {m: U[m]["all"]["tps_median"] for m in MAIN}
COST = {m: U[m]["all"]["cost"] for m in MAIN}
CPS = {m: sum(U[m][t]["cost"] for t in TIERS[:4]) / sum(1 for r in SAMP[m].values() if r["tier"] != "L5" and r["solved"])
       for m in MAIN}
for m in MAIN:  # the per-solved cost of the cost table (合计 = L1-L4 only)
    assert abs(CPS[m] - U[m]["all"]["cost_per_solved"]) < 1e-6, (m, CPS[m], U[m]["all"]["cost_per_solved"])


# ---------------------------------------------------------------- 概览
def index():
    cols = []
    for m in MAIN:
        u = U[m]["all"]
        cols.append(f"""<div class="model"><div>{dot(m)}<h3>{mname(m)}</h3><div class="id">{API[m]}</div></div>
<div class="big">{L14[m]:.1f}%</div><div class="cap">L1–L4 pass@1{UP}</div>
{specs([(f"{L4P[m]:.1f}%", "L4 pass@1" + UP), (f"{L5S[m]:.1f}", "L5 平均得分（参考解 60）" + UP),
        (f"{u['tps_median']:.1f}", "输出速度 tokens/s" + UP), (f"{u['ttft_median']:.1f} 秒", "首个 token" + DN),
        (f"{u['lat_median']:.0f} 秒", "延迟中位数" + DN), (usd(u['cost']), "全部 202 个采样的费用" + DN),
        (usd(CPS[m], 3), "每份解出答案（L1–L4）" + DN)])}</div>""")
    e4, e5 = E["L4"], E["L5"]
    hp = pair(KIMI, HIGH, "L4")
    body = f"""<section class="hero"><div class="wrap">
<p class="eyebrow">codingBench 阶梯评测 · {DATE}</p>
<h1>代码能力阶梯评测</h1>
<p class="lead">以人类竞赛组别为难度标尺的五档、112 道题：<span class="nw">Kimi K3.1 Pro</span>、<span class="nw">DeepSeek Flash V4.1-1017</span> 与 <span class="nw">MiniMax M3.1 Flash</span> 的正确率、思考强度、运行效率与费用。</p>
<div class="ctas"><a class="btn" href="results.html">查看结果</a><a class="more" href="{REPORT}">技术报告（PDF）</a><a class="more" href="custom.html">自定义评测</a></div>
</div></section>
<section class="section alt"><div class="wrap">
<h2>三个模型</h2>
<p class="sub">L1–L4 为 USACO 铜、银、金、铂金组与 EGOI 2026，按官方时限判题；L5 为 FrontierCS 开放式难题，按 0–100 连续计分。Kimi K3.1 Pro 在 L1–L3 为 auto，L4–L5 为 max。</p>
<div class="compare" style="--rows:10">{''.join(cols)}</div>
<p class="note">{LEGEND}。输出速度、首个 token 与延迟为每次调用的中位数；费用按各家官方美元标价计算；每份解出答案的费用为 L1–L4 的费用除以解出的采样数。</p>
</div></section>
<section class="section"><div class="wrap">
<h2>要点</h2>
<p class="sub">数字均来自本次评测记录，计算方法见“原理”，完整分析见技术报告。</p>
<div class="tiles">
<a class="card" href="results.html#main"><p class="k">差距集中在 L4</p><p class="v">{L4P[KIMI]:.1f}%</p>
<p>Kimi 的 L4 pass@1；DeepSeek {L4P[DS]:.1f}%，MiniMax {L4P[MM]:.1f}%。L1–L4 合计 {L14[KIMI]:.1f}%、{L14[DS]:.1f}% 与 {L14[MM]:.1f}%，三组两两差值都显著。</p></a>
<a class="card" href="results.html#effort"><p class="k">思考强度</p><p class="v">{sg(hp['diff'])} 个百分点</p>
<p>Kimi 由 high 改为 max，L4 的 pass@1 由 {L4P[HIGH]:.1f}% 升至 {L4P[KIMI]:.1f}%（95% 区间 {ci(hp['ci'])}）；L5 的平均得分只变化 {sg(e5['diff'])} 分（区间 {ci(e5['ci'])}）。</p></a>
<a class="card" href="results.html#main"><p class="k">L5 开放式难题</p><p class="v">{L5S[KIMI]:.1f} 分</p>
<p>Kimi 的 L5 平均得分；DeepSeek {L5S[DS]:.1f}，MiniMax {L5S[MM]:.1f}。官方参考解为 {REF_L5} 分，没有一个答案在全部测试点上取得满分。</p></a>
<a class="card" href="results.html#cost"><p class="k">速度与费用</p><p class="v">{TPS[KIMI]:.1f} tokens/s</p>
<p>Kimi 的输出速度中位数，DeepSeek {TPS[DS]:.1f}、MiniMax {TPS[MM]:.1f}。完成全部评测的费用为 {usd(COST[KIMI])}、{usd(COST[DS])} 与 {usd(COST[MM])}。</p></a>
<div class="card wide"><p class="k">结论</p>
<p>Kimi K3.1 Pro 与 DeepSeek Flash V4.1-1017 在 L3 上的 pass@1 都在 95% 以上，模型之间的差距从 L4 开始拉开。Kimi 的领先依赖 max 思考强度：high 下它的 L4 pass@1 为 {L4P[HIGH]:.1f}%，低于 DeepSeek。它的领先也以速度与费用为代价，输出速度不到另外两个模型的五分之一，每份解出答案的费用约为它们的 {CPS[KIMI] / max(CPS[DS], CPS[MM]):.0f} 倍。三个模型在 L5 上都远低于官方参考解。</p></div>
</div>
</div></section>"""
    assert M[KIMI]["L3"]["pass1"] > 95 and M[DS]["L3"]["pass1"] > 95 and L4P[HIGH] < L4P[DS]
    assert TPS[KIMI] * 5 < min(TPS[DS], TPS[MM])
    page("index.html", "代码能力阶梯评测 · BAI AI Lab", body,
         "Kimi K3.1 Pro、DeepSeek Flash V4.1-1017、MiniMax M3.1 Flash 在 codingBench 阶梯评测（L1–L5，112 题）上的结果")


# ---------------------------------------------------------------- 题目
def composition():
    rows = []
    for t in TIERS:
        by = collections.OrderedDict()
        for p in sorted(D["tiers"][t], key=lambda q: META[q]["source"] != "usaco"):
            by.setdefault(META[p]["source"], []).append(p)
        for i, (s, ps) in enumerate(by.items()):
            dates = sorted(META[p]["date"] for p in ps)
            when = "题库 v1.1" if s == "frontiercs" else (dates[0] if dates[0] == dates[-1] else f"{dates[0]} 至 {dates[-1]}")
            rows.append((' class="grp"' if i == len(by) - 1 else "",
                         [(TN[t] if i == 0 else "", "nw"), (source(ps[0]), "nw"), (str(len(ps)), "n"), (when, "nw"),
                          (LANG[META[ps[0]]["lang"]], "nw"), (SCORING[META[ps[0]]["scoring"]["type"]], "nw")]))
    rows.append([("合计", ""), ("", ""), (str(len(ORDER)), "n"), ("", ""), ("", ""), ("", "")])
    return table([("档位", ""), ("来源", ""), ("题数", "n"), ("比赛时间", ""), ("作答语言", ""), ("计分", "")], rows)


def problems():
    rows = []
    for p in ORDER:
        m = META[p]
        rows.append((f' data-tier="{m["tier"]}" data-source="{m["source"]}" data-href="p/{p}.html"',
                     [(f'<a class="mono" href="p/{p}.html">{p}</a>', "nw"), (esc(title(p)), ""), (m["tier"], "nw"),
                      (contest(p), "nw hide-sm"), (m["date"], "nw hide-sm")]))

    def seg(name, opts):
        return (f'<div class="seg" data-filter="{name}">' + "".join(
            f'<button aria-pressed="{str(i == 0).lower()}" data-value="{v}">{t}</button>' for i, (v, t) in enumerate(opts)) + "</div>")

    body = f"""<section class="section tight"><div class="wrap">
<h2>题目</h2>
<p class="sub">五档共 {len(ORDER)} 题。L1–L4 是 USACO 2024–25、2025–26 两个赛季的铜、银、金、铂金组与 EGOI 2026，组别由真实选手的晋级线划定；L5 是 FrontierCS 算法赛道中没有已知最优解的开放式难题。测试数据与参考解都来自官方发布。</p>
{composition()}
<p class="note">USACO 每个组别计划 21 题，建库校验时剔除了没有官方解能通过、有多个合法答案却没有 checker 等无法可靠判分的题。EGOI 2026 的 2 道交互题与 IOI 2026 的题目未纳入。FrontierCS 题库 180 题，按题号均匀抽取 30 题。</p>
<h3 id="all">全部 {len(ORDER)} 题</h3>
<div class="filters">
{seg("tier", [("all", "全部档位")] + [(t, t) for t in TIERS])}
{seg("source", [("all", "全部来源"), ("usaco", "USACO"), ("egoi2026", "EGOI 2026"), ("frontiercs", "FrontierCS")])}
</div>
{table([("题号", ""), ("题目", ""), ("档位", ""), ("比赛", "hide-sm"), ("日期", "hide-sm")], rows, "plist")}
<p class="note">点击一行查看题意概述、原题链接、各模型的得分与代码。</p>
</div></section>"""
    page("problems.html", "题目 · 代码能力阶梯评测", body, f"codingBench 阶梯评测的 {len(ORDER)} 道题：组成、题意概述与原题链接")


def sample_line(m, q):
    r = SAMP[m][q]
    k = int(q.split("#")[1]) + 1
    if r["solved"]:
        return f'<span class="ok">{r["score"]:.0f}</span>', f"采样 {k} · 解出"
    return f'<span class="{"bad" if r["score"] == 0 else ""}">{r["score"]:.1f}</span>', f"采样 {k} · {FAILN.get(r['fail'], r['fail'])}"


def problem_page(i, p):
    meta = META[p]
    t = meta["tier"]
    ms = models_in(t)
    tl = time_limit(p)
    rec = {"id": p, "title": title(p), "tier": t, "source": source(p), "contest": contest(p), "date": meta["date"],
           "language": LANG[meta["lang"]], "scoring": SCORING[meta["scoring"]["type"]], "time_limit_s": tl, "url": url(p),
           "summary": SUMMARY[p], "results": {}}
    parts = [f"""<section class="section tight"><div class="wrap">
<p class="crumb"><a href="../problems.html">题目</a> › <span class="mono">{p}</span></p>
<h1 class="ptitle">{esc(title(p))}</h1>
<p class="meta">{contest(p)} · {meta['date']} · <span class="pill">{TN[t]}</span> · {LANG[meta['lang']]}{f' · 时限 {tl:g} 秒' if tl else ''} · {SCORING[meta['scoring']['type']]}</p>
<p class="summary">{esc(SUMMARY[p])}</p>
<p><a class="btn" href="{url(p)}" target="_blank" rel="noopener">查看原题</a></p>
</div></section>"""]
    cols, tabs, panels = [], [], []
    lexer = PythonLexer() if meta["lang"] == "python" else CppLexer()
    nrows = 0
    for j, m in enumerate(ms):
        qs = samples(m, p)
        rs = [SAMP[m][q] for q in qs]
        mean = statistics.mean(r["score"] for r in rs)
        solved = sum(r["solved"] for r in rs)
        items = [f"<li><b>{v}</b><span>{lab}</span></li>" for v, lab in (sample_line(m, q) for q in qs)]
        outs = [r["out"] for r in rs if r["out"] is not None]
        tps = [r["tps"] for r in rs if r["tps"]]
        lat = [r["latency"] for r in rs if r["latency"] is not None]
        ratios = [PERF[m][q]["ratio"] for q in qs if q in PERF[m] and PERF[m][q].get("ratio")]
        cls_ = collections.Counter(CPLXN.get(CPLXR[m][q]["time"]["class"], CPLXR[m][q]["time"]["class"]) for q in qs if q in CPLXR[m])
        nums = [(ktok(statistics.mean(outs)) if outs else "—", "平均输出 token（含思考）" + DN),
                (f(statistics.median(tps)) if tps else "—", "输出速度 tokens/s" + UP),
                (f"{statistics.median(lat):.0f} 秒" if lat else "—", "延迟" + DN)]
        if meta.get("ref"):  # USACO: compared with the fastest official solution
            nums.append((f"{math.exp(statistics.mean(math.log(x) for x in ratios)):.2f}×" if ratios else "—", "CPU 时间 / 官方解" + DN))
            nums.append(("、".join(f"{k} {v}" if len(qs) > 1 else k for k, v in cls_.items()) if cls_ else "—", "时间复杂度（相对官方解）"))
        if meta["lang"] == "python":
            ql = [QUAL[m][q] for q in qs if q in QUAL[m] and QUAL[m][q].get("pylint")]
            nums += [(f(statistics.mean(x["pylint"]["total"] for x in ql), 0) if ql else "—", "Pylint 问题" + DN),
                     (f(statistics.mean(x["pylint"]["score"] for x in ql), 2) if ql else "—", "Pylint 得分" + UP),
                     (f(statistics.mean(x["radon"]["complexity"] for x in ql), 0) if ql else "—", "圈复杂度" + DN),
                     (f(statistics.mean(x["radon"]["mi"] for x in ql)) if ql else "—", "可维护性指数" + UP)]
        items += [f"<li><b>{v}</b><span>{lab}</span></li>" for v, lab in nums]
        nrows = 3 + len(items)
        big = f"{mean:.1f}" if t == "L5" else f"{solved}/{len(qs)}"
        cap = "平均得分" + UP if t == "L5" else ("解出的采样" + UP)
        cols.append(f"""<div class="model"><div>{dot(m)}<h3>{mname(m)}</h3><div class="id">{effort(m, t)}</div></div>
<p class="verdict {'ok' if solved == len(qs) else 'bad' if mean == 0 else ''}">{big}</p><p class="cap">{cap}</p><ul class="specs">{''.join(items)}</ul></div>""")
        tabs.append(f'<button aria-pressed="{str(j == 0).lower()}" data-value="{CLS[m]}">{SHORT[m]}</button>')
        stabs, spanels = [], []
        res = []
        for k, q in enumerate(qs):
            code = ANS[m][q].get("code") or ""
            r = SAMP[m][q]
            sid = f"code-{CLS[m]}-{k}"
            if code.strip():
                inner = (f'<div class="codehead"><span class="cap">{dot(m)} {NAME[m]} · 采样 {k + 1} · {len(code.splitlines())} 行</span>'
                         f'<button class="copy" data-src="{sid}">复制代码</button></div>'
                         f'<div id="{sid}">{highlight(code, lexer, HtmlFormatter(cssclass="code"))}</div>')
            else:
                inner = '<div class="empty">没有代码：回答中没有代码块。</div>'
            spanels.append(f'<div data-panel-group="s-{CLS[m]}" data-panel="{k}"{"" if k == 0 else " hidden"}>{inner}</div>')
            stabs.append(f'<button aria-pressed="{str(k == 0).lower()}" data-value="{k}">采样 {k + 1}</button>')
            res.append({"sample": k + 1, "score": r["score"], "solved": r["solved"], "failure": r["fail"],
                        "output_tokens": r["out"], "latency_s": None if r["latency"] is None else round(r["latency"], 1),
                        "ttft_s": None if r["ttft"] is None else round(r["ttft"], 2),
                        "tokens_per_s": None if r["tps"] is None else round(r["tps"], 1),
                        "cpu_ratio_vs_official": round(PERF[m][q]["ratio"], 3) if q in PERF[m] and PERF[m][q].get("ratio") else None,
                        "time_complexity": CPLXR[m][q]["time"]["class"] if q in CPLXR[m] else None, "code": code})
        seg = f'<div class="samples"><div class="seg sm" data-tabs="s-{CLS[m]}">{"".join(stabs)}</div></div>' if len(qs) > 1 else ""
        panels.append(f'<div data-panel-group="code" data-panel="{CLS[m]}"{"" if j == 0 else " hidden"}>{seg}{"".join(spanels)}</div>')
        rec["results"][m] = {"name": NAME[m], "reasoning_effort": effort(m, t), "samples": res}
    parts.append(f"""<section class="section alt"><div class="wrap">
<h2>结果</h2>
<div class="compare small{' four' if len(ms) == 4 else ''}" style="--rows:{nrows}">{''.join(cols)}</div>
<p class="note">{LEGEND}。得分 0–100，按官方时限判定，所有测试点都满分才算解出。CPU 时间 / 官方解为解出的答案在官方解最慢的 3 个测试点上的 CPU 时间之比（几何平均），只比较官方解至少需要 0.05 秒的题；复杂度按增长幂次相对官方解分类。判题与计分见 <a href="../method.html#judge">原理</a>。</p>
</div></section>
<section class="section"><div class="wrap">
<div class="codehead"><h2>代码</h2><div class="seg" data-tabs="code">{''.join(tabs)}</div></div>
{''.join(panels)}
</div></section>""")
    prev_p, next_p = (ORDER[i - 1] if i else None), (ORDER[i + 1] if i + 1 < len(ORDER) else None)
    pager = (f'<a href="{prev_p}.html">‹ {prev_p}</a>' if prev_p else "<span></span>") + \
            (f'<a href="{next_p}.html">{next_p} ›</a>' if next_p else "<span></span>")
    parts.append(f'<div class="wrap"><nav class="pager">{pager}</nav></div>')
    page(f"p/{p}.html", f"{p} {title(p)} · 代码能力阶梯评测", "\n".join(parts), f"{p} {title(p)}：{SUMMARY[p]}", "code.css")
    return rec


# ---------------------------------------------------------------- 结果
def chart():
    """pass@1 of L1-L4 and L1-L4 combined, mean score of L5, with the 95% intervals."""
    cats = [("L1", "pass1"), ("L2", "pass1"), ("L3", "pass1"), ("L4", "pass1"), ("L1-L4", "pass1"), ("L5", "score")]
    W, top, bottom, left, right = 760, 24, 250, 40, 8
    span = bottom - top
    out = ['<defs><pattern id="hatch" class="hatch" patternUnits="userSpaceOnUse" width="5" height="5" '
           'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5"/></pattern></defs>']
    for v in (0, 20, 40, 60, 80, 100):
        y = bottom - span * v / 100
        out.append(f'<line class="grid" x1="{left}" x2="{W - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{v}</text>')
    gw, bw, gap = (W - left - right) / len(cats), 22, 4
    for i, (t, key) in enumerate(cats):
        ms = models_in(t) if t != "L1-L4" else MAIN
        cx = left + gw * (i + 0.5)
        x0 = cx - (len(ms) * bw + (len(ms) - 1) * gap) / 2
        if t == "L5":
            y = bottom - span * REF_L5 / 100
            out.append(f'<line class="ref" x1="{cx - gw / 2 + 6:.1f}" x2="{cx + gw / 2 - 6:.1f}" y1="{y:.1f}" y2="{y:.1f}"/>'
                       f'<text x="{cx + gw / 2 - 6:.1f}" y="{y - 5:.1f}" text-anchor="end">参考解 {REF_L5}</text>')
        for j, m in enumerate(ms):
            v = M[m][t]
            val, lo, hi = v[key], *v[f"{key}_ci"]
            x = x0 + j * (bw + gap)
            h = span * val / 100
            out.append(f'<rect class="{CLS[m]}" x="{x:.1f}" y="{bottom - h:.1f}" width="{bw}" height="{h:.1f}" rx="3"/>')
            out.append(f'<line class="whisker" x1="{x + bw / 2:.1f}" x2="{x + bw / 2:.1f}" y1="{bottom - span * lo / 100:.1f}" '
                       f'y2="{bottom - span * hi / 100:.1f}"/>')
        label = {"L1-L4": "L1–L4", "L5": "L5（得分）"}.get(t, t)
        out.append(f'<text class="cat" x="{cx:.1f}" y="{bottom + 22}" text-anchor="middle">{label}</text>')
    legend = "".join(f'<li><i class="{CLS[m]}-bg"></i>{NAME[m]}</li>' for m in ALL)
    return (f'<svg class="chart" viewBox="0 0 {W} {bottom + 32}" role="img" aria-label="各档 pass@1 与 L5 平均得分（%，95% 区间）">'
            + "".join(out) + f'</svg><ul class="legend">{legend}</ul>')


def main_table():
    groups = []
    for t in TIERS + ["L1-L4"]:
        ms = models_in(t) if t != "L1-L4" else MAIN
        v = {m: M[m][t] for m in ms}
        bp = max((x.get("pass1", -1) for x in v.values()), default=None)
        bs = max(x["score"] for x in v.values())
        rr = []
        for m in ms:
            x = v[m]
            p1 = bold(x.get("pass1"), bp, f"{x['pass1']:.1f} <span class=\"sec\">{ci(x['pass1_ci'])}</span>") if "pass1" in x else ("—", "n")
            sc = bold(x["score"], bs, f"{x['score']:.1f}" + (f" <span class=\"sec\">{ci(x['score_ci'])}</span>" if "score_ci" in x else ""))
            rr.append([mcell(m), (effort(m, t) if t != "L1-L4" else "", "nw"), (str(x["n_samples"]), "n"), p1, sc,
                       (f(x["passn"]) if "passn" in x and t in ("L3", "L4") else "—", "n")])
        groups.append((TN[t], rr))
    return table([("档位", ""), ("模型", ""), ("思考强度", ""), ("采样数", "n"), ("pass@1（%）" + UP, "n"), ("平均得分" + UP, "n"),
                  ("pass@3（%）" + UP, "n")], tiered(groups))


def pairwise_table():
    pairs = [(KIMI, DS), (KIMI, MM), (DS, MM)]
    head = [("档位", "")]
    for a, b in pairs:
        head += [(f"{SHORT[a]} − {SHORT[b]}", "n"), ("胜/平/负", "n")]
    rows = []
    for t in ["L1", "L2", "L3", "L4", "L1-L4", "L5"]:
        cells = [(TN[t], "nw")]
        for a, b in pairs:
            x = pair(a, b, t)
            cells += [(f"{sg(x['diff'])}{'*' if sig(x['ci']) else ''} <span class=\"sec\">{ci(x['ci'])}</span>", "n best" if sig(x["ci"]) else "n"),
                      (f"{x['wins']}/{x['ties']}/{x['losses']}" if "wins" in x else "—", "n")]
        rows.append((' class="grp"' if t in ("L4", "L1-L4") else "", cells))
    return table(head, rows)


def effort_tables():
    rows = []
    for t, lab in (("L4", "L4（high 下输出有误的采样）"), ("L5", "L5（全部采样）")):
        x = E[t]
        rows.append([(lab, ""), (str(x["n"]), "n"), (f"{x['high_solved']} → {x['max_solved']}" if t == "L4" else "—", "n"),
                     (f"{x['high_mean']:.1f} → {x['max_mean']:.1f}", "n"),
                     (f"{sg(x['diff'])}{'*' if sig(x['ci']) else ''} <span class=\"sec\">{ci(x['ci'])}</span>", "n"),
                     (f"{x['up']}/{x['n'] - x['up'] - x['down']}/{x['down']}，{pv(x['p'])}", "n")])
    t1 = table([("比较范围", ""), ("采样数", "n"), ("解出 high → max", "n"), ("平均得分 high → max", "n"), ("差值 [95% 区间]", "n"),
                ("提高/持平/降低", "n")], rows)
    groups = []
    for t in ("L4", "L5"):
        x = E[t]
        groups.append((t, [[(k, "nw"), (ktok(x[k + "_out"]), "n"), (f(x[k + "_tps"]), "n"), (f"{x[k + '_lat'] / 60:.1f}", "n")]
                           for k in ("high", "max")]))
    t2 = table([("档位", ""), ("思考强度", ""), ("每次输出 token" + DN, "n"), ("输出速度 tokens/s" + UP, "n"), ("延迟中位数（分钟）" + DN, "n")],
               tiered(groups))
    return t1, t2


def subsets_table():
    sub = {"2026": "EGOI 2026", "USACO 2024-25": "USACO 2024–25", "USACO 2025-26": "USACO 2025–26"}
    groups = []
    for t in ("L3", "L4"):
        rr = []
        for s in ("2026", "USACO 2024-25", "USACO 2025-26"):
            k = f"{t}|{s}"
            if k not in AGG[KIMI]["subsets"]:
                continue
            cells = [(sub[s], "nw"), (str(AGG[KIMI]["subsets"][k]["problems"]), "n")]
            for m in ALL:
                x = AGG[m]["subsets"].get(k)
                cells.append((f(x["pass1"]) if x and m in models_in(t) else "—", "n"))
            rr.append(cells)
        groups.append((t, rr))
    return table([("档位", ""), ("子集", ""), ("题数", "n")] + [(f"{dot(m)} {SHORT[m]}", "n") for m in ALL], tiered(groups))


def perf_tables():
    groups = []
    for t in ("L1", "L2", "L3", "L4"):
        rr = []
        for m in models_in(t):
            v = AGG[m]["tiers"][t]
            rr.append([mcell(m), (str(v["perf_n"]), "n"), (f"{v['perf_geo']:.2f}×", "n"), (str(v["perf_faster"]), "n"),
                       (str(v["perf_2x"]), "n"), (f"{v['mem_geo']:.2f}×", "n")])
        groups.append((t, rr))
    t1 = table([("档位", ""), ("模型", ""), ("比较的答案数", "n"), ("CPU 时间倍数" + DN, "n"), ("快于官方解" + UP, "n"), ("慢 2 倍以上" + DN, "n"),
                ("峰值内存倍数" + DN, "n")], tiered(groups))
    groups = []
    for t in ("L1", "L2", "L3", "L4"):
        rr = []
        for m in models_in(t):
            c = (AGG[m]["complexity"].get(t) or {}).get("time")
            if c:
                rr.append([mcell(m)] + [(str(c["classes"].get(k, 0)), "n") for k, _ in CPLX] + [(f(c["k_median"], 2), "n")])
        groups.append((t, rr))
    t2 = table([("档位", ""), ("模型", "")] + [(n, "n") for _, n in CPLX] + [("k 中位数", "n")], tiered(groups))
    return t1, t2


def failures_table():
    groups = []
    for t in TIERS:
        rr = []
        for m in models_in(t):
            fl = AGG[m]["tiers"][t]["fails"]
            n = sum(1 for r in SAMP[m].values() if r["tier"] == t)
            rr.append([mcell(m), (str(n), "n"), (str(sum(fl.values())), "n")] + [(str(fl.get(k, 0)), "n") for k, _ in FAIL])
        groups.append((t, rr))
    return table([("档位", ""), ("模型", ""), ("答案数", "n"), ("未解出" + DN, "n")] + [(n, "n") for _, n in FAIL], tiered(groups))


def quality_table():
    Q = [("pylint_issues", "Pylint 问题数" + DN, 2, min), ("pylint_score", "Pylint 得分" + UP, 2, max),
         ("issues_per_100sloc", "每百行问题数" + DN, 2, min), ("cc", "圈复杂度" + DN, 2, min), ("mi", "可维护性 MI" + UP, 1, max),
         ("sloc", "SLOC", 1, None)]
    qs = {m: AGG[m]["quality"]["correct"] for m in MAIN}
    rows = []
    for m in MAIN:
        cells = [mcell(m), (str(qs[m]["n"]), "n")]
        for k, _, nd, best in Q:
            v = qs[m][k]
            cells.append(bold(v, best([qs[x][k] for x in MAIN]) if best else None, f(v, nd)))
        rows.append(cells)
    return table([("模型", ""), ("答案数", "n")] + [(n, "n") for _, n, _, _ in Q], rows)


def cost_table():
    groups = []
    for t in TIERS + ["all"]:
        rr = []
        for m in (models_in(t) if t != "all" else ALL):
            u = U[m][t]
            cps = u.get("cost_per_solved")
            rr.append([mcell(m), (str(u["calls"]), "n"), (f"{u['out_sum'] / 1e6:.2f}M", "n"), (ktok(u["out_mean"]), "n"),
                       (f(u["tps_median"]), "n"), (f(u["ttft_median"]), "n"), (f"{u['lat_median']:.0f}", "n"), (usd(u["cost"]), "n"),
                       ("—" if t == "L5" or not cps else usd(cps, 3), "n")])
        groups.append((TN[t], rr))
    return table([("档位", ""), ("模型", ""), ("调用数", "n"), ("输出 token" + DN, "n"), ("每次输出" + DN, "n"), ("tokens/s" + UP, "n"),
                  ("首 token 秒" + DN, "n"), ("延迟 秒" + DN, "n"), ("费用" + DN, "n"), ("每份解出" + DN, "n")], tiered(groups))


def attribution_table():
    kd4, km4, dm, dm3, dm4 = pair(KIMI, DS, "L4"), pair(KIMI, MM, "L4"), pair(DS, MM, "L1-L4"), pair(DS, MM, "L3"), pair(DS, MM, "L4")
    hp, e5 = pair(KIMI, HIGH, "L4"), E["L5"]
    out = {m: U[m]["all"]["out_mean"] for m in MAIN}
    r = lambda c, d, o, v: [(c, ""), (d, "nw"), (o, ""), (v, "nw")]  # noqa: E731
    blk = lambda m: (' class="blk"', [(NAME[m], ""), ("", ""), ("", ""), ("", "")])  # noqa: E731
    same = "本评测为单轮、单文件、无工具的作答"
    rows = [
        blk(KIMI),
        r("以大规模强化学习增强长程编程（Kimi Code Bench 3.0 长程 61.2，K3 为 55.95）", "多轮、多文件编程", same, "超出测量范围"),
        r("智能体编程（Terminal-Bench 4.0 65.7）", "多轮、带工具", "同上", "超出测量范围"),
        r("官方成绩以 max 思考强度取得", "思考强度", f"max 相对 high：L4 pass@1 {sg(hp['diff'])} {ci(hp['ci'])}；L5 平均得分 {sg(e5['diff'])} {ci(e5['ci'])}",
          "L4 一致；L5 差异不显著"),
        r("Highspeed 版本速度为 K3.1 Pro 的 2–3 倍", "生成速度", f"本站评测的是 kimi-k3.1-pro，输出速度中位数 {TPS[KIMI]:.1f} tokens/s", "超出测量范围"),
        r("没有竞赛编程方面的声称或成绩", "竞赛编程",
          f"L4 领先 DeepSeek {sg(kd4['diff'])} {ci(kd4['ci'])}、领先 MiniMax {sg(km4['diff'])} {ci(km4['ci'])}；L5 领先 "
          f"{sg(pair(KIMI, DS, 'L5')['diff'])} 与 {sg(pair(KIMI, MM, 'L5')['diff'])}", "无对应声称"),
        blk(DS),
        r("Codeforces 评分 3471（内部评测，max 深度），高于 V4-Flash 的 3289 与 V4-Pro 的 3348", "竞赛编程",
          f"相对 MiniMax：L1–L4 合计 {sg(dm['diff'])} {ci(dm['ci'])}，L3 {sg(dm3['diff'])} {ci(dm3['ci'])}，L4 {sg(dm4['diff'])} {ci(dm4['ci'])}；"
          f"相对 Kimi：L4 {sg(-kd4['diff'])}", "一致，可归因（相对 MiniMax）"),
        r("1017 版以自反馈强化学习改进端到端项目开发；智能体编程（DeepSWE v1.1 77.0、Terminal-Bench 4.0 42.3）", "多轮、多文件编程", same,
          "超出测量范围"),
        r("1017 版缩短输出长度与任务耗时（相对 0910 版）", "输出长度",
          f"每次调用平均输出 {ktok(out[DS])} token，长于 Kimi 的 {ktok(out[KIMI])}、短于 MiniMax 的 {ktok(out[MM])}；没有 0910 版对照", "无法检验"),
        r("按思考深度施加长度惩罚、深度可调", "思考强度", "本评测使用接口默认的 high，没有比较不同深度", "超出测量范围"),
        blk(MM),
        r("输出速度可达每秒 200 token 以上、中位数 170 以上", "生成速度", f"输出速度中位数 {TPS[MM]:.1f} tokens/s，低于所称；DeepSeek 为 {TPS[DS]:.1f}",
          "不一致"),
        r("智能体编程与工具调用（DeepSWE v1.1 73.7、Terminal Bench 4.0 38.1）；交错思考", "多轮、带工具", same, "超出测量范围"),
        r("在线推理快近 3 倍、使用成本降低 70%（相对前代）", "费用", f"没有前代对照；本评测费用 {usd(COST[MM])}，高于 DeepSeek 的 {usd(COST[DS])}", "无法检验"),
        r("没有竞赛编程方面的声称或成绩", "竞赛编程", "L3、L4 的 pass@1 均显著落后 DeepSeek 与 Kimi（见上）", "无对应声称"),
    ]
    assert sig(hp["ci"]) and not sig(e5["ci"]) and sig(dm["ci"]) and sig(dm3["ci"]) and sig(dm4["ci"]) and TPS[MM] < 170
    assert out[KIMI] < out[DS] < out[MM] and COST[MM] > COST[DS] and sig(pair(KIMI, MM, "L3")["ci"])
    return table([("厂商声称", ""), ("对应维度", ""), ("本评测观测", ""), ("判定", "")], rows)


def matrix():
    head = [("题号", ""), ("题目", "hide-sm"), ("档位", "")] + [(f"{dot(m)} {SHORT[m]}", "n") for m in ALL]
    rows = []
    for p in ORDER:
        t = META[p]["tier"]
        cells = [(f'<a class="mono" href="p/{p}.html">{p}</a>', "nw"), (esc(title(p)), "hide-sm"), (t, "nw")]
        for m in ALL:
            if m not in models_in(t):
                cells.append(("—", "n"))
                continue
            rs = [SAMP[m][q] for q in samples(m, p)]
            solved = sum(r["solved"] for r in rs)
            if t == "L5":
                cells.append((f"{rs[0]['score']:.1f}", "n"))
            elif len(rs) == 1:
                cells.append(('<span class="ok">✓</span>' if solved else f'<span class="bad">✗</span> <span class="sec">{FAILN[rs[0]["fail"]]}</span>', "n"))
            else:
                cells.append((f'<span class="{"ok" if solved == len(rs) else "bad" if solved == 0 else ""}">{solved}/{len(rs)}</span>', "n"))
        rows.append(cells)
    return table(head, rows)


def results():
    t_eff1, t_eff2 = effort_tables()
    t_perf, t_cplx = perf_tables()
    kd, km, dm = (pair(KIMI, DS, "L1-L4"), pair(KIMI, MM, "L1-L4"), pair(DS, MM, "L1-L4"))
    kda, kma, dma = (pair(KIMI, DS, "all"), pair(KIMI, MM, "all"), pair(DS, MM, "all"))
    e4, e5 = E["L4"], E["L5"]
    hp = pair(KIMI, HIGH, "L4")
    f12 = {m: AGG[m]["tiers"]["L1"]["fails"] for m in MAIN}
    ds_low = [r for r in SAMP[DS].values() if r["tier"] in ("L1", "L2") and not r["solved"]]
    assert ds_low and all(r["fail"] == "TLE" for r in ds_low)
    sub = {m: {k: AGG[m]["subsets"][k]["pass1"] for k in AGG[m]["subsets"]} for m in ALL}
    body = f"""<section class="section tight"><div class="wrap">
<h2 id="main">结果</h2>
<p class="sub">L1、L2、L5 每题采样 1 次，L3、L4 每题采样 3 次，每个模型共 202 个采样。方括号内为按题重抽样的 95% 区间。{LEGEND}，粗体为每档最优。</p>
{chart()}
<p class="note">L1–L4 为 pass@1（%），L5 为平均得分（连续分）；竖线为 95% 区间；斜线柱为 Kimi K3.1 Pro 在 high 思考强度下的结果；虚线为 FrontierCS 官方参考解的 {REF_L5} 分。</p>
<h3>各档正确率</h3>
{main_table()}
<p class="note">pass@1 为解出的采样占全部采样的比例，平均得分为全部采样得分（0–100）的平均，pass@3 为 3 次采样中至少解出一次的题所占比例，只适用于 L3、L4。L5 为连续分，只报告平均得分。</p>
<ul class="list">
<li><b>Kimi K3.1 Pro 的 L1–L4 合计 pass@1 最高，差距集中在 L4。</b>L1–L4 合计三者为 {L14[KIMI]:.1f}%、{L14[DS]:.1f}% 与 {L14[MM]:.1f}%；L4 上为 {L4P[KIMI]:.1f}%、{L4P[DS]:.1f}% 与 {L4P[MM]:.1f}%。L3 上 Kimi 与 DeepSeek 分别为 {M[KIMI]['L3']['pass1']:.1f}% 与 {M[DS]['L3']['pass1']:.1f}%，pass@3 三者都是 100%。</li>
<li><b>DeepSeek 在 L1、L2 的失分全部来自官方时限。</b>它在这两档没有解出的 {len(ds_low)} 个采样都是输出正确、但 CPU 时间超过官方时限的 Python 答案。</li>
<li><b>L5 三个模型都远低于参考解。</b>平均得分为 {L5S[KIMI]:.1f}、{L5S[DS]:.1f} 与 {L5S[MM]:.1f}，官方参考解为 {REF_L5} 分。</li>
</ul>
<h3 id="pairwise">差距是否可信？</h3>
{pairwise_table()}
<p class="note">L1–L4 与合计为 pass@1 之差（百分点），L5 为平均得分之差；方括号内为配对 bootstrap 的 95% 区间，* 与粗体表示区间不含 0。胜/平/负为逐题比较的题数（每题所有采样的平均得分，相差不到 0.05 分记为持平）。</p>
<ul class="list">
<li><b>三组差距在 L1–L4 合计上都显著。</b>Kimi 领先 DeepSeek {kd['diff']:.1f} 个百分点 {ci(kd['ci'])}，领先 MiniMax {km['diff']:.1f} 个百分点 {ci(km['ci'])}；DeepSeek 领先 MiniMax {dm['diff']:.1f} 个百分点 {ci(dm['ci'])}。逐题比较全部 {len(ORDER)} 题，胜负分别为 {kda['wins']} 比 {kda['losses']}（{pv(kda['p'])}）、{kma['wins']} 比 {kma['losses']}（{pv(kma['p'])}）与 {dma['wins']} 比 {dma['losses']}（{pv(dma['p'])}）。</li>
<li><b>显著差距出现在 L3 以上。</b>L1、L2 的差值区间都含 0；Kimi 与 DeepSeek 在 L3 上没有差别，在 L4 与 L5 上 Kimi 显著领先；DeepSeek 与 MiniMax 的差距在 L3、L4 上显著，在 L5 上不显著。</li>
</ul>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="effort">思考强度</h2>
<p class="sub">Kimi K3.1 Pro 在 L4、L5 上的 high 与 max。high 一组以 high 作答全部 84 个采样；max 一组中，L5 的 30 个采样与 L4 中 high 下输出有误的 {e4['n']} 个采样以 max 作答，L4 其余 {54 - e4['n']} 个采样沿用 high 的答案。</p>
{t_eff1}
<p class="note">差值为 max 减 high 的平均得分，方括号内为按采样重抽样的 95% 区间；提高/持平/降低按得分变化是否达到 0.05 分计，p 为精确符号检验。</p>
<h3>输出长度、速度与延迟</h3>
{t_eff2}
<p class="note">与上表为同一批采样。输出 token 含思考；速度与延迟为中位数。</p>
<ul class="list">
<li><b>max 显著提高了 L4，对 L5 没有显著影响。</b>L4 的 pass@1 由 high 的 {L4P[HIGH]:.1f}% 升至 max 的 {L4P[KIMI]:.1f}%，差 {hp['diff']:.1f} 个百分点 {ci(hp['ci'])}；high 下输出有误的 {e4['n']} 个采样中，max 解出 {e4['max_solved']} 个。L5 的平均得分由 {e5['high_mean']:.1f} 变为 {e5['max_mean']:.1f}，差 {sg(e5['diff'])} 分 {ci(e5['ci'])}。</li>
<li><b>max 的输出更长，速度不变。</b>每次调用的平均输出 token 在 L4 为 high 的 {e4['max_out'] / e4['high_out']:.1f} 倍，在 L5 为 {e5['max_out'] / e5['high_out']:.1f} 倍；延迟随输出长度同步增加。</li>
<li><b>思考强度改变了 L4 的排名。</b>high 的 {L4P[HIGH]:.1f}% 介于 DeepSeek（{L4P[DS]:.1f}%）与 MiniMax（{L4P[MM]:.1f}%）之间，max 的 {L4P[KIMI]:.1f}% 则高于两者。</li>
</ul>
<h3 id="subsets">新题是否明显更难？</h3>
{subsets_table()}
<p class="note">pass@1（%）。EGOI 2026 发布于 2026 年 5 月，晚于 USACO 的全部比赛。</p>
<ul class="list">
<li><b>最新的 EGOI 2026 题没有比旧题更差。</b>Kimi 与 DeepSeek 解出了 EGOI 2026 的全部 18 个采样，MiniMax 为 {sub[MM]['L3|2026']:.1f}%，与其 L3 的 USACO 2024–25 子集（{sub[MM]['L3|USACO 2024-25']:.1f}%）相当。</li>
<li><b>L4 上 USACO 2025–26 赛季的题对三个模型都更难。</b>Kimi 由 {sub[KIMI]['L4|USACO 2024-25']:.1f}% 降至 {sub[KIMI]['L4|USACO 2025-26']:.1f}%，DeepSeek 由 {sub[DS]['L4|USACO 2024-25']:.1f}% 降至 {sub[DS]['L4|USACO 2025-26']:.1f}%，MiniMax 由 {sub[MM]['L4|USACO 2024-25']:.1f}% 降至 {sub[MM]['L4|USACO 2025-26']:.1f}%。</li>
</ul>
</div></section>
<section class="section"><div class="wrap">
<h2 id="perf">运行效率</h2>
<p class="sub">只比较解出的答案，与官方解在同一台机器、同一语言下比较；倍数为各档的几何平均，小于 1 表示快于官方解。EGOI 与 FrontierCS 没有官方解，不参与比较。</p>
{t_perf}
<p class="note">取官方解最慢的 3 个测试点，答案与官方解交替各运行 3 次取中位数；只比较官方解在某个测试点上至少需要 0.05 秒 CPU 的题。三个模型解出的题并不相同，这一比较只针对各自解出的答案。</p>
<h3>时间复杂度（相对官方解，答案数）</h3>
{t_cplx}
<p class="note">以官方解自身的耗时作为规模的度量，拟合 log y<sub>答案</sub> = a + k · log y<sub>官方</sub>；R² ≥ 0.8 时才下结论：k ≤ 0.75 且在最重的 3 个测试点上至少快 2 倍为更优，0.75 &lt; k &lt; 1.33 为同阶，k ≥ 1.33 且至少慢 2 倍为更差。k 中位数只统计更优、同阶与更差三类。</p>
<h3 id="fail">答案为什么没有解出？</h3>
{failures_table()}
<p class="note">每份答案只记一个主要原因，判定顺序为无代码、生成超时、编译错误、答案错误、运行错误、超时、部分分；生成超时指接口在返回答案前断开；L5 为连续计分，得分大于 0 的答案记为部分分。</p>
<h3 id="quality">静态代码质量</h3>
{quality_table()}
<p class="note">L1、L2 中解出的 Python 答案，每份平均；工具与版本按 Huang 等人（arXiv:2610.19167）：Pylint 3.3.5 与 Radon 6.0.1。每列较好者加粗，SLOC 只描述代码长短。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="cost">用量、速度与费用</h2>
<p class="sub">每个采样一次调用。Kimi 每次调用的输出最短，但输出速度最慢、费用最高；DeepSeek 与 MiniMax 的费用相近。</p>
{cost_table()}
<p class="note">输出 token 含思考；tokens/s 为输出速度；输出速度、首个 token 时间与延迟为中位数；费用按各家官方美元标价计算（见 <a href="method.html#setup">原理 › 调用设置</a>）；每份解出答案的费用为该档费用除以解出的采样数，合计只算 L1–L4。</p>
<h3 id="claims">厂商声称与本评测观测</h3>
{attribution_table()}
<p class="note">差值为该模型减去对比模型（百分点或分），方括号内为配对 bootstrap 的 95% 区间。判定规则见 <a href="method.html#attr">原理 › 归因规则</a>；归因说明观测与声称是否相符，不说明因果。</p>
</div></section>
<section class="section"><div class="wrap">
<h2 id="matrix">逐题结果</h2>
<p class="sub">L1、L2 为单次采样的结果，L3、L4 为 3 次采样中解出的次数，L5 为得分。点题号查看各模型的代码。</p>
{matrix()}
<h3>局限性</h3>
<ul class="list">
<li><b>调用参数不对等。</b>DeepSeek 使用接口默认的 high，Kimi 与 MiniMax 以 max 为主；采样参数也不同：Kimi 使用接口默认的 temperature 与 top_p，DeepSeek 在思考模式下忽略 temperature，MiniMax 为 0.2。</li>
<li><b>L4 的 max 结果部分沿用 high 的答案。</b>L4 中 high 下输出正确的 {54 - e4['n']} 个采样没有以 max 重新作答，max 一组对这些采样的结果等于 high。</li>
<li><b>归因是观测上的一致，而非因果。</b>三个模型在数据、规模与训练方法上同时不同，本评测既没有消融实验，也没有评测它们的前代。</li>
<li><b>题目覆盖不全。</b>EGOI 的 2 道交互题与 IOI 2026 的题目没有纳入；高档题量少，L3、L4 只有 27 与 18 题，区间较宽。</li>
<li><b>效率比较存在选择偏差。</b>运行效率与代码质量只比较各自解出的答案，三个模型解出的题并不相同。</li>
<li><b>费用与速度依赖调用条件。</b>费用按公开标价计算，不代表订阅或折扣后的实际支出；输出速度受并发与网络条件影响。</li>
</ul>
</div></section>"""
    assert all(f12)  # noqa
    page("results.html", "结果 · 代码能力阶梯评测", body, "各档正确率、两两比较、思考强度、运行效率、失败类型、代码质量、用量与费用")


# ---------------------------------------------------------------- 原理
def method():
    c = cite
    setup = table([("模型", ""), ("API 名称", ""), ("思考强度", ""), ("输出上限", "n"), ("单价（美元 / 百万 token）", "")], [
        [mcell(KIMI), ("<code>kimi-k3.1-pro</code>", "nw"), ("L1–L3：auto（max）；L4–L5：max", ""), ("262,144；max 为 1,046,528", "n"),
         ("2.00 / 0.20 / 10.00", "nw")],
        [mcell(HIGH), ("<code>kimi-k3.1-pro</code>", "nw"), ("L4–L5：high", ""), ("262,144", "n"), ("2.00 / 0.20 / 10.00", "nw")],
        [mcell(DS), ("<code>deepseek-flash</code>", "nw"), ("L1–L5：auto（high）", ""), ("262,144", "n"), ("0.30 / 0.006 / 1.20（非高峰半价）", "nw")],
        [mcell(MM), ("<code>MiniMax-M3.1-Flash</code>", "nw"), ("L1–L5：auto（max）；L4 中 9 个、L5 中 1 个采样为 high", ""), ("262,144", "n"),
         ("0.15 / 0.015 / 0.60", "nw")],
    ])
    body = f"""<section class="section tight"><div class="wrap">
<h2>原理</h2>
<p class="sub">以人类竞赛的组别为难度标尺，从官方来源构建五档题库；按官方时限判题，与官方解比较运行效率与复杂度，并报告输出 token、输出速度与费用。</p>
<div class="steps">
<div class="card"><h4>建库</h4><p>下载官方题面、测试数据与题解，用判题程序运行全部官方解；没有官方解能通过的题剔除。</p></div>
<div class="card"><h4>生成</h4><p>每个采样调用一次模型，取回答中最后一个对应语言的代码块。</p></div>
<div class="card"><h4>判题</h4><p>在评测机本机按官方时限运行全部测试点，按来源的官方规则计分。</p></div>
<div class="card"><h4>效率与质量</h4><p>与官方解比较 CPU 时间、内存与复杂度增长幂次；Python 档另测静态代码质量。</p></div>
<div class="card"><h4>统计</h4><p>按题重抽样的 bootstrap 区间、配对差值与逐题符号检验。</p></div>
</div>
<h3 id="bench">阶梯基准</h3>
<ul class="list">
<li><b>难度用人类标尺划分。</b>USACO {c('usaco')} 的铜、银、金、铂金四个组别由真实选手的晋级线划定，EGOI {c('egoi')} 是国际奥赛；档位反映的是人类选手的水平，而不是某个模型觉得难不难。</li>
<li><b>只用官方数据。</b>AtCoder 自 2024 年 12 月起不再公开测试数据，LeetCode 的测试不公开且用户协议禁止批量抓取，这两个来源都给不出可信的标准答案，因此没有采用。</li>
<li><b>高档用连续分。</b>USACO 按测试点给部分分，EGOI 按子任务给分，FrontierCS {c('frontiercs', 'frontiercsrepo')} 由 checker 给出连续分，高档不会像通过率那样很快饱和。</li>
<li><b>按官方时限判题。</b>每个测试点按实际 CPU 时间判定是否在官方时限内完成，与人类选手的判题条件一致。</li>
<li><b>先验证判题本身。</b>建库时先用判题程序运行官方题解；没有任何一份官方解能全部通过的题直接剔除，这同时检验了测试数据、比对规则与判题程序。能通过的官方解中最快的一份作为该题的性能对照。</li>
</ul>
<p>USACO 取 2024–25 赛季的 12 月、1 月、2 月与美国公开赛共 4 场，以及 2025–26 赛季的 3 场线上赛（3 月的公开赛为线下监考赛，官网没有公布题目与测试数据）。EGOI 2026 共 8 题，其中 Census 与 Seating Plan 为交互题，不在题库中。IOI 2026 的题目为通信题或只提供 PDF 题面，未纳入。FrontierCS 的题库有 180 道开放式难题，没有类别标签，按题号均匀抽取 30 题。题面与测试数据只存放在评测服务器上，不进入代码仓库；仓库只记录题号、档位、日期与时限。各档组成见 <a href="problems.html">题目</a>。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="judge">判题与计分</h2>
<p class="sub">判题在评测服务器本机进行，所有模型使用同一套题目、判题程序与计分规则。</p>
<ul class="list">
<li><b>运行环境。</b>答案以无特权用户运行，由一个小的启动器设置地址空间（内存上限加 64 MB）、栈、CPU 时间与输出大小（256 MB）上限，并把进程绑定在一个独占的核上；CPU 时间与峰值内存取自子进程自身的资源统计。CPU 时间超过官方时限的测试点判为超时。</li>
<li><b>语言。</b>Python 档使用 CPython 3.11、只允许标准库，官方时限沿用 USACO 给 Python 的时限；C++ 档以 <code>g++ -O2 -std=gnu++17</code> 编译。</li>
<li><b>比对。</b>USACO 忽略空白逐个 token 比对，与其官方规则一致；EGOI 使用官方 checker；FrontierCS 使用官方的 testlib checker 或交互器，并照搬其判分规则，只解析 checker 输出的得分比例。</li>
</ul>
<h3>计分</h3>
<p>每个测试点 t 得分 s<sub>t</sub> ∈ [0, 1]：编译失败、运行出错、超时或超内存记 0。每题得分 S（0–100）按来源的官方规则计算：</p>
<ul class="list">
<li>USACO：S = 100 · (1/T) · Σ<sub>t</sub> s<sub>t</sub>，即测试点等分。</li>
<li>EGOI：S = 100 · Σ<sub>g</sub> w<sub>g</sub> · min<sub>t∈g</sub> s<sub>t</sub> / Σ<sub>g</sub> w<sub>g</sub>，即子任务 g 取其中测试点的最低分，再乘以子任务分值。</li>
<li>FrontierCS：所有测试点得分比例的平均乘以 100；达到参考解为 60 分，超过参考解越多得分越高。</li>
</ul>
<p>所有测试点都满分才算“解出”。L1、L2、L5 每题采样 1 次，L3、L4 每题采样 3 次，以减小高档题少带来的随机误差。pass@1 {c('humaneval')} 是解出的采样占全部采样的比例，平均得分是全部采样的 S 的平均，pass@3 是 3 次采样中至少一次解出的题所占比例。L5 为连续分，只报告平均得分。</p>
</div></section>
<section class="section"><div class="wrap">
<h2 id="perf">运行效率、复杂度与代码质量</h2>
<p class="sub">与 EffiBench {c('effibench')}、ENAMEL {c('enamel')} 一样，只在答案正确的前提下比较效率；基准是官方解，而不是模型之间互相比较 {c('perfbench')}。</p>
<ul class="list">
<li><b>运行效率。</b>只对解出的答案、且官方解在某个测试点上至少需要 0.05 秒 CPU 的题比较运行时间：取官方解最慢的 3 个测试点，答案与官方解交替各运行 3 次取中位数，倍数为答案的 CPU 时间除以官方解的 CPU 时间，各档取几何平均。峰值内存倍数同理。</li>
<li><b>复杂度。</b>官方测试点未按规模排列，USACO 中耗时可测的测试点几乎都是最大规模，直接按输入大小拟合不可行 {c('bigobench')}。因此以官方解自身的耗时作为规模的度量：在官方解至少需要 2 ms CPU 的测试点上（最多 20 个，均匀覆盖其耗时范围），答案与官方解交替各运行 5 次取中位数，拟合 log y<sub>答案</sub> = a + k · log y<sub>官方</sub>。若官方解为 Θ(f(n))、答案为 Θ(f(n)<sup>k</sup>)，k 即为这个指数。只在 R² ≥ 0.8 时下结论：k ≤ 0.75 且在官方解最重的 3 个测试点上答案至少快 2 倍为更优，0.75 &lt; k &lt; 1.33 为同阶，k ≥ 1.33 且至少慢 2 倍为更差，其余为不确定；可用测试点少于 4 个或官方耗时跨度不足 4 倍为不可测。</li>
<li id="static"><b>静态代码质量。</b>对 L1、L2 中解出的 Python 答案，按 Huang 等人 {c('staticquality')} 的工具与版本，报告 Pylint 3.3.5 的问题数与 0–10 分，以及 Radon 6.0.1 的圈复杂度、可维护性指数（MI）与代码行数（SLOC）。</li>
<li><b>用量、速度与费用。</b>每个采样对应一次调用。输出 token 为接口计费的输出用量，含思考过程；延迟为调用从发出到接收完毕的时间；首个 token 时间为从发出到收到第一个 token 的时间；输出速度为输出 token 除以首个 token 之后的时长（tokens/s）。费用按各家的官方美元标价计算：（输入 − 缓存命中）× 输入单价 + 缓存命中 × 命中单价 + 输出 × 输出单价，分时计价按每次调用的开始时间。</li>
</ul>
<h3 id="stats">统计方法</h3>
<p>模型之间的比较以题目为单位。各档指标的 95% 区间来自 B = 2000 次按题重抽样（随机种子 0）{c('efron1979')}：每次在每档内部有放回地抽取同样数量的题，重新计算各档与 L1–L4 合计的 pass@1 与平均得分，取 2.5% 与 97.5% 分位数；两个模型使用同一组题（配对 bootstrap），从而消除题目难度带来的共同波动。逐题比较取每题所有采样的平均得分，相差不到 0.05 分记为持平，并对胜负题数做精确符号检验。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="setup">调用设置</h2>
<p class="sub">三个模型都通过各自厂商的官方接口流式调用。MiniMax 的 temperature 为 0.2、top_p 为 0.95（沿用 LiveCodeBench 的设置）；DeepSeek 在思考模式下不支持 temperature 参数 {c('dsapi')}；Kimi 不传 temperature 与 top_p，使用接口默认值。</p>
{setup}
<p class="note">单价依次为输入（缓存未命中）、缓存命中与输出；DeepSeek 在北京时间非高峰时段半价，费用按每次调用的开始时间计算。auto 表示请求中不指定思考强度，括号内为接口默认值。</p>
<p><b>思考强度。</b>三家接口都提供思考强度参数（<code>reasoning_effort</code>）。请求中不指定思考强度、由接口采用默认值的设置记为 auto：Kimi {c('kimieffort')} 与 MiniMax 的默认值为 max，DeepSeek 的默认值为 high。Kimi 在 L4、L5 上给出 high 与 max 两组结果：high 一组以 high 作答全部 84 个采样；max 一组中，L5 的 30 个采样与 L4 中 high 下输出有误的 18 个采样以 max 作答，L4 其余 36 个采样沿用 high 的答案。</p>
<h3 id="prompts">提示词</h3>
<p>USACO 与 EGOI 题沿用 LiveCodeBench {c('lcb')} 的写法，并给出时限与内存限制；FrontierCS 使用其官方生成脚本的原始提示词，便于与其公开排行榜对照。答案取回答中最后一个对应语言的代码块，没有对应语言时取最后一个代码块。</p>
<ul class="list">
<li>Python 档系统提示词：<code>You are an expert Python programmer. You will be given a question (problem specification) and will generate a correct Python program that matches the specification and passes all tests.</code></li>
<li>C++ 档系统提示词：<code>You are an expert competitive programmer. You will be given a question (problem specification) and will generate a correct and efficient C++17 program that matches the specification and passes all tests.</code></li>
<li>用户消息：<code>### Question:</code> 之后为题面，随后一行写明时限、内存限制与语言（如 <code>Time limit: 2 seconds per test. Memory limit: 256 MB. Compiled with g++ -O2 -std=gnu++17.</code>），再给出格式说明：<code>Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on the sample inputs). Enclose your code within delimiters as follows.</code></li>
<li>FrontierCS：<code>You are a competitive programmer. You will be given a problem statement, please implement a solution in C++. The execution time and memory limit are also stated in the statement so be aware of the complexity of the program. Please wrap the code in ```cpp and ``` so that it is properly formatted. Your response should ONLY contain the C++ code, with no additional explanation or text.</code></li>
</ul>
</div></section>
<section class="section"><div class="wrap">
<h2 id="models">被测模型</h2>
<p class="sub">三个模型都在 2026 年 9–10 月发布，都默认开启思考。以下内容来自厂商的技术博客、技术报告、模型卡与接口文档，分数为厂商自报。</p>
<h3>Kimi K3.1 Pro</h3>
<p>月之暗面于 2026 年 10 月 23 日发布，官方称它是 Kimi K3 的后训练版本，使用了大得多的后训练算力，并在数百个下游领域上联合做强化学习 {c('kimik31')}；K3 为 MoE 架构，总参数 2.8T、每 token 激活 104B，上下文 1M {c('kimik3')}。代码方面，官方称 K3.1 Pro 覆盖从真实代码库中的快速修复到完整项目构建的全部编程工作，并以大规模强化学习增强长程编程；自报 Terminal-Bench 4.0 65.7%（Claude Code 框架），内部的 Kimi Code Bench 3.0 长程子集 61.2%（K3 为 55.95%）。官方成绩使用 max 思考强度、temperature 1.0、top-p 0.95；另有 Highspeed 版本（<code>kimi-k3.1-pro-highspeed</code>），称速度为 K3.1 Pro 的 2–3 倍。思考不能关闭，强度可选 low、high、max，不指定时默认 max {c('kimieffort')}。官方没有报告竞赛编程成绩。</p>
<h3>DeepSeek Flash V4.1-1017</h3>
<p>DeepSeek 于 2026 年 9 月 10 日发布 V4.1-Flash，10 月 17 日更新为 1017 版，接口名与价格不变，以 MIT 许可开放权重 {c('ds1017')}。模型为多模态 MoE，主干 552B 参数、每 token 激活 8B（prefill）/ 16B（decode），另有 196B 的 Engram 条件记忆，上下文 1M。技术报告 {c('dsv41')} 的主要创新在注意力与 KV cache 的压缩，面向长上下文与“输入很重”的智能体场景的服务成本；报告明确说后训练“没有算法上的创新”，沿用监督微调、强化学习与在线蒸馏的标准流程，改动都在数据上，并在训练中按思考深度施加长度惩罚，使深度可调。报告称其 Codeforces 评分（内部评测）为 3471，高于 V4-Flash 的 3289 与 V4-Pro 的 3348。1017 版称以自反馈强化学习改进端到端的项目开发，并缩短了任务耗时与输出长度；厂商自报（智能体框架）Terminal-Bench 4.0 由 31.2 提高到 42.3、DeepSWE v1.1 由 74.2 提高到 77.0、ProgramBench 由 20.3 提高到 29.1。官方评测使用最高思考深度，接口不指定时默认为 high {c('dsapi')}。</p>
<h3>MiniMax M3.1 Flash</h3>
<p>MiniMax 于 2026 年 10 月 19 日上线接口、10 月 23 日开放权重；MoE 架构，总参数约 428B、每 token 激活约 23B，上下文 1M，思考不能关闭，不指定时默认最高深度 {c('minimaxm31')}。厂商称 M3.1 Flash 沿用前代 M3 的核心架构，只做了三处改动：全部层改为稀疏注意力，路由专家与注意力路径做量化感知训练，以 DSpark 投机解码代替原先的多 token 预测。这三处都面向推理速度与成本：官方称输出速度可达每秒 200 token 以上、中位数稳定在 170 以上，在线推理快近 3 倍、使用成本降低 70%。厂商把它定位于智能体任务，称其原生支持在每轮工具调用之间思考（交错思考），自报 DeepSWE v1.1 73.7、Terminal Bench 4.0 38.1、NL2Repo-Bench 61.2；前代 M3 自报 SWE-Bench Verified 80.5 {c('minimaxm3')}。</p>
<p>三家都没有报告与本评测题源重合的成绩（USACO、EGOI 或 FrontierCS）：DeepSeek 的技术报告只在思考深度的曲线图中给出 LiveCodeBench（未注明版本、没有数值表），Kimi 与 MiniMax 没有报告竞赛编程成绩。</p>
<h3 id="attr">归因规则</h3>
<p>厂商声称的改进大多相对其上一代模型而言，而本评测没有评测它们的前代，因此不检验“是否比前代更好”，而检验较弱的命题：厂商声称擅长或改进的方向，在本评测对应的测量上是否表现为显著的相对优势。一条声称同时满足以下两点时，记为一致，可归因：</p>
<ul class="list">
<li>厂商指明了它针对的能力，且能对应到某个档位或某项测量（正确率、运行效率、生成速度、输出长度等）；</li>
<li>在这项测量上，该模型相对另一个模型的差值显著（区间不含 0），方向与声称一致；对于可直接测量的绝对数值（如生成速度），测量值与声称相符。</li>
</ul>
<p>方向相反或测量值与声称不符时记为不一致；对应不到本评测测量的声称（如多轮的智能体编程）记为超出测量范围；只是相对前代的数量声称，记为无法检验；观测到显著差异但没有对应声称的，记为无对应声称，不作归因。三个模型在数据、规模与训练方法上同时不同，本评测没有消融实验，这种归因说明观测与声称是否相符，不说明因果。对照结果见 <a href="results.html#claims">结果 › 厂商声称</a>。</p>
</div></section>"""
    agent_tbl = table([("", ""), ("单次生成（本评测）", ""), ("智能体评测", "")], [
        [("输入", "nw"), ("题目描述", ""), ("任务描述 + 可操作的环境（代码仓库、终端）", "")],
        [("模型做什么", "nw"), ("回复一次，给出完整程序", ""), ("循环“思考 → 调用工具（读文件、改代码、执行命令、跑测试）→ 观察结果”，直到提交", "")],
        [("环境", "nw"), ("无；判题在模型之外进行", ""), ("每个任务一个隔离容器，固定代码版本与依赖", "")],
        [("判定", "nw"), ("全部测试点满分", ""), (f"提交后在干净环境中运行隐藏测试；SWE-bench 要求原本失败的测试变为通过（FAIL_TO_PASS），且原本通过的测试仍通过（PASS_TO_PASS）{c('swebench')}", "")],
        [("结果取决于", "nw"), ("模型", ""), (f"模型 + 外壳（scaffold：工具集、提示词、上下文管理、步数上限）{c('sweagent', 'effi')}", "")],
        [("代表", "nw"), (f"LiveCodeBench {c('lcb')}、HumanEval {c('humaneval')}", ""), (f"SWE-bench {c('swebench')}、SWE-bench Verified {c('verified')}、Terminal-Bench {c('tbench')}", "")],
    ])
    body += f"""
<section class="section alt"><div class="wrap">
<h2 id="agent">智能体（agent）评测</h2>
<p class="sub">本评测是单次生成：模型读题后一次写出程序。智能体评测让模型在可执行的环境里多步行动，按最终结果判定。</p>
{agent_tbl}
<h3>评测智能体的要点</h3>
<ul class="list">
<li>环境可复现：每个任务固定代码版本、依赖和镜像，智能体与判题在同一份环境中运行。SWE-bench 取自 12 个流行 Python 仓库的 2,294 个真实 issue 与对应的修复 {c('swebench')}；Terminal-Bench 2.0 的 89 个终端任务各带独立环境、人工参考解和自动测试 {c('tbench')}。</li>
<li>按结果判定，测试要充分：提交后由环境之外的隐藏测试判定。测试不足会把错误补丁判为通过：SWE-bench Verified 中 26/500 题测试不足 {c('utboost')}；被判为通过的补丁有 7.8% 跑不过开发者的完整测试 {c('wang')}。SWE-bench Verified 本身是 93 名开发者从原题中筛出的 500 题 {c('verified')}。</li>
<li>测试对智能体隐藏：智能体能看到或修改测试时会走捷径。ImpossibleBench 把测试改成与题意矛盾，能“通过”即说明作弊；能力更强的模型作弊率更高，把测试对模型隐藏后作弊率接近 0 {c('impossible')}。</li>
<li>外壳与模型一起报告：同一模型换外壳，解决率和花费都会变 {c('sweagent', 'effi')}。</li>
<li>同时报告成本：只比准确率会鼓励昂贵的智能体，应给出准确率与成本（token、美元、时间）的取舍 {c('matter', 'hal')}。</li>
<li>警惕污染：只给 issue 文本、不给代码，模型在 SWE-bench 的仓库上猜中出错文件的准确率最高 76%，换成其他仓库只有 53% {c('illusion')}。</li>
</ul>
</div></section>"""
    refs = []
    for i, k in enumerate(REF_ORDER):
        text, link = BIB[k] if k in BIB else AGENT_REFS[k]
        a = f' <a href="{link}">{esc(link.split("://", 1)[1])}</a>' if link and link not in text else ""
        refs.append(f'<li id="ref-{i + 1}">{esc(text)}{a}</li>')
    body += f"""
<section class="section"><div class="wrap">
<h2 id="refs">参考文献</h2>
<ol class="refs">{''.join(refs)}</ol>
</div></section>"""
    page("method.html", "原理 · 代码能力阶梯评测", body, "阶梯基准、判题与计分、运行效率与复杂度、统计方法、调用设置、被测模型、归因规则与参考文献")


# ---------------------------------------------------------------- 自定义评测
def cmd(cid, text):
    return (f'<div class="cmd"><button class="copy" data-src="{cid}">复制</button>'
            f'<pre class="code" id="{cid}"><code>{esc(text)}</code></pre></div>')


def custom():
    params = table([("变量", ""), ("默认", "nw"), ("作用", ""), ("怎么选", "")], [
        [("<code>MODEL</code>", "nw"), ("必填", "nw"), ("平台上的模型名，也用作运行目录名（其中的 / 换成 _）", ""), ("按平台文档，如 <code>deepseek-flash</code>、<code>kimi-k3.1-pro</code>", "")],
        [("<code>OPENAI_BASE_URL</code>", "nw"), ("必填", "nw"), ("OpenAI 兼容接口地址，以 <code>/v1</code> 结尾", ""), ("按平台文档", "")],
        [("<code>OPENAI_API_KEY</code>", "nw"), ("必填", "nw"), ("平台的 API key", ""), ("用 <code>read -rs</code> 输入，不写进命令行、脚本或仓库", "")],
        [("<code>REASONING_EFFORT</code>", "nw"), ("不传", "nw"), ("请求里的 <code>reasoning_effort</code>，如 <code>low</code>、<code>high</code>、<code>max</code>", ""),
         ("不设即 auto，由接口采用默认值；要比较思考强度时每档各跑一次", "")],
        [("<code>LADDER_N</code>", "nw"), ("<code>L1=1,L2=1,L3=3,L4=3,L5=1</code>", "nw"), ("每档每题的采样次数", ""), ("保持默认，与本站可比", "")],
        [("<code>MAX_TOKENS</code>", "nw"), ("不传", "nw"), ("每次回答的最大 token 数，含思考", ""), ("推理模型设成平台允许的最大输出，或保持不传，由平台决定", "")],
        [("<code>WORKERS</code>", "nw"), ("16", "nw"), ("同时发出的请求数", ""), ("按平台限流调；遇到 429 就调小", "")],
        [("<code>STREAM</code>", "nw"), ("1", "nw"), ("流式请求，记录首个 token 的时间与输出速度", ""), ("保持默认；平台不支持流式时设 <code>0</code>", "")],
        [("<code>LADDER_TIMEOUT</code>", "nw"), ("300 秒", "nw"), ("流式：两次收到 token 之间的最长间隔；<code>STREAM=0</code> 时为整个回答的超时（默认 1800 秒）", ""), ("保持默认", "")],
        [("<code>TEMPERATURE</code>", "nw"), ("0.2", "nw"), ("采样温度（LiveCodeBench 的设置）", ""), ("平台固定采样参数时用 <code>LADDER_OMIT</code> 去掉", "")],
        [("<code>LADDER_OMIT</code>", "nw"), ("无", "nw"), ("请求里不发送的字段，逗号分隔", ""), ("如 Kimi K3.1 Pro：<code>temperature,top_p</code>", "")],
        [("<code>PRICE_IN</code>、<code>PRICE_HIT</code>、<code>PRICE_OUT</code>", "nw"), ("不设", "nw"),
         ("每百万 token 的单价（输入未命中缓存 / 命中缓存 / 输出，思考算输出），用来算费用和每份解出答案的费用", ""),
         ("按平台价目填；分时计价的平台再设 <code>PRICE_OFF_IN</code>、<code>PRICE_OFF_HIT</code>、<code>PRICE_OFF_OUT</code>（非高峰单价）和 <code>PEAK_HOURS_UTC</code>", "")],
        [("<code>CB_POST</code>", "nw"), ("1", "nw"), ("生成结束后自动判题、复测性能、拟合复杂度、统计静态质量并写报告", ""), ("保持默认；设 <code>0</code> 跳过，之后用 <code>cb ladder-post</code> 补跑", "")],
    ])
    fixed = table([("项目", ""), ("固定为", "")], [
        [("题单", "nw"), (f"本站的 {len(ORDER)} 题，题号见 <a href=\"problems.html\">题目</a> 与 <code>data/ladder.json</code>；服务器上的清单由 <code>cb ladder-build --manifest</code> 生成", "")],
        [("提示词", "nw"), ("USACO、EGOI 沿用 LiveCodeBench 的写法；FrontierCS 用其官方提示词（见 <a href=\"method.html#prompts\">原理 › 提示词</a>）", "")],
        [("判题", "nw"), ("官方时限、官方测试数据与 checker，按来源的官方规则计分", "")],
        [("运行效率与复杂度", "nw"), ("与官方解在同一台机器上交替运行比较", "")],
        [("静态代码质量", "nw"), ("L1、L2 的 Python 答案：Pylint 3.3.5、Radon 6.0.1", "")],
    ])
    cost_rows = [[mcell(m), (f"{U[m]['all']['out_sum'] / 1e6:.2f}M", "n"), (usd(U[m]["all"]["cost"]), "n")] for m in MAIN]
    presets = cmd("c5", """# 例如 Kimi K3.1 Pro 的 max（平台固定采样参数）
export REASONING_EFFORT=max LADDER_OMIT=temperature,top_p MAX_TOKENS=1046528 \\
       PRICE_IN=2 PRICE_HIT=0.2 PRICE_OUT=10

# 例如 DeepSeek Flash V4.1-1017（分时计价）
export MAX_TOKENS=262144 PRICE_IN=0.3 PRICE_HIT=0.006 PRICE_OUT=1.2 \\
       PRICE_OFF_IN=0.15 PRICE_OFF_HIT=0.003 PRICE_OFF_OUT=0.6""")  # outside the f-string: Python 3.11 allows no backslash in one
    body = f"""<section class="section tight"><div class="wrap">
<h2>自定义评测</h2>
<p class="sub">在实验室服务器上用 codingBench 的 <code>cb ladder</code> 评测任意 OpenAI 兼容接口的模型，题目、判题与计分与本站相同。模型写的代码会在服务器上执行，所有评测都以无特权用户 <code>bench</code> 运行。</p>
<h3>准备</h3>
<ul class="list">
<li>服务器账号：地址、端口和账号向实验室管理员索取，本站不公开。需要 root 或有 sudo 权限的账号（<code>cb</code> 会切换到 <code>bench</code> 用户运行）。</li>
<li>模型接口：OpenAI 兼容的接口地址、模型名和 API key，以及足够的账户余额（费用估算见下文）。</li>
<li>题目数据已经在服务器上建好；在新机器上复现时，先运行 <code>cb ladder-data</code> 下载官方数据，再运行 <code>cb ladder-build --calibrate</code> 建库并用官方解校验。</li>
</ul>
<h3>1. 登录</h3>
{cmd("c1", "ssh -p <端口> <用户名>@<服务器地址>")}
<h3>2. 设置模型</h3>
{cmd("c2", '''export MODEL=<模型名>                        # 例如 deepseek-flash
export OPENAI_BASE_URL=https://<平台地址>/v1
read -rsp "API key: " OPENAI_API_KEY && export OPENAI_API_KEY && echo   # 粘贴后回车；不显示，也不进命令历史''')}
<p>推理模型和平台限制较多的模型，按下面的参数手册加上对应设置，例如：</p>
{presets}
<h3>3. 冒烟测试</h3>
{cmd("c3", "cb ladder --smoke      # 每档只跑第一题、采样 1 次，先确认接口、格式和扣费正常")}
<h3>4. 正式运行</h3>
{cmd("c4", '''nohup cb ladder > ~/ladder.log 2>&1 &     # 断开 SSH 也继续跑
cb progress <模型名>/ladder-full --watch 30  # 已答的采样、出错、每个进行中的请求
cb ladder --tiers L4,L5                     # 只跑部分档位；--only usaco-1452,fcs-85 只跑指定的题''')}
<h3>5. 结果</h3>
<p>生成结束后，<code>cb</code> 自动依次判题、复测运行效率、拟合复杂度、统计静态质量并写报告。运行目录在安装目录的 <code>runs/&lt;模型名&gt;/ladder-full/</code>，报告在其中的 <code>report/report.md</code>。</p>
{cmd("c6", '''cb ladder-post <模型名>/ladder-full                      # 跳过了后处理（CB_POST=0）或中途中断时补跑
cb ladder-report <模型A>/ladder-full <模型B>/ladder-full --out <目录>
                       # 几个模型放在一份报告里对比''')}
<h3>6. 中断与续跑</h3>
<p>直接重跑同一条命令：已经答过的采样不会再请求，判题在本机进行，不花钱。</p>
</div></section>
<section class="section alt"><div class="wrap">
<h2 id="manual">参数手册</h2>
<p class="sub">全部通过环境变量设置，在运行 <code>cb</code> 前 <code>export</code>。</p>
{params}
<h3>固定不变的设置</h3>
{fixed}
<h3>费用估算</h3>
<p>费用 ≈ 输入 token × 输入单价 + 输出 token × 输出单价。输入只有题面，输出 token 主要是思考，不同模型差别很大。本站全部 202 个采样的实际用量：</p>
{table([("模型", ""), ("输出 token", "n"), ("费用（美元）", "n")], cost_rows)}
<h3>常见问题</h3>
<ul class="list">
<li>报 400 参数错误：平台不接受某些请求字段，用 <code>LADDER_OMIT</code> 去掉。</li>
<li>429 限流：调小 <code>WORKERS</code>。</li>
<li>余额不足：运行暂停，已答的采样保留；充值后重跑同一条命令补齐。</li>
<li>其他 benchmark：<code>cb livecodebench</code>（LiveCodeBench，见 <a href="{ARCHIVE}">上一版评测</a>）、<code>cb bigcodebench</code>、<code>cb cruxeval</code>。</li>
</ul>
</div></section>"""
    page("custom.html", "自定义评测 · 代码能力阶梯评测", body, "在服务器上用 codingBench 评测自己的模型：cb ladder 的命令与参数手册")


def assets():
    a = os.path.join(OUT, "assets")
    os.makedirs(a, exist_ok=True)
    for name in ("style.css", "app.js"):
        shutil.copy(os.path.join(HERE, "site_assets", name), a)
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
    for old in ("report-2026-10-23.pdf",):  # the previous evaluation lives under archive/ now
        if os.path.exists(os.path.join(OUT, old)):
            os.remove(os.path.join(OUT, old))
    assets()
    method()  # first: it numbers the references
    index()
    problems()
    results()
    custom()
    probs = [problem_page(i, p) for i, p in enumerate(ORDER)]
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    data = {
        "date": DATE,
        "benchmark": "codingBench ladder: L1-L4 USACO 2024-26 (Bronze, Silver, Gold, Platinum) and EGOI 2026, L5 FrontierCS algorithmic",
        "judging": "official time limits, official tests and checkers; score 0-100 per problem, solved = every test at full score",
        "samples_per_problem": {"L1": 1, "L2": 1, "L3": 3, "L4": 3, "L5": 1},
        "models": [{"id": m, "name": NAME[m], "api_model": API[m],
                    "tiers": {t: {k: M[m][t].get(k) for k in ("n_problems", "n_samples", "pass1", "pass1_ci", "score", "score_ci", "passn")}
                              for t in M[m]},
                    "usage": U[m]["all"]} for m in ALL],
        "problems": probs,
    }
    json.dump(data, open(os.path.join(OUT, "data", "ladder.json"), "w"), ensure_ascii=False, indent=1)
    shutil.copy(os.path.join(HERE, "main.pdf"), os.path.join(OUT, REPORT))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("pages:", 5 + len(probs), "->", OUT)


if __name__ == "__main__":
    main()
