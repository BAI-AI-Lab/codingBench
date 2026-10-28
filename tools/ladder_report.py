"""Report of one or more ladder runs: Markdown + LaTeX (+ PDF when xelatex is installed).

  python ladder_report.py <run dir> [<run dir> ...] --out <report dir> [--date 2026-11-01]
     prices per 1M tokens per run: PRICE_IN/PRICE_HIT/PRICE_OUT (one model) or --prices model=in,hit,out;...

Per model and tier: pass@1 (share of samples that pass every test) and the mean score (0-100, the source's partial
credit rule), each under the lenient limit (algorithm right) and the official limit (also fast enough); pass@n
where a tier has several samples; the 2026 subset (EGOI/IOI) next to the USACO problems of the same tiers as a
contamination check; failure types; runtime against the official solution (perf.jsonl); static quality of the
Python tiers (quality.jsonl); tokens, latency and cost (usage.jsonl). Writes report.json, report.md, data.tex,
main.tex and build.sh in --out; the PDF needs xelatex with Times New Roman and Kaiti (on the Mac: bash build.sh).
"""
import argparse
import collections
import datetime
import json
import math
import os
import shutil
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402
import lcb_usage as U  # noqa: E402

TIER_NAME = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式"}
FAIL_ORDER = ("no code", "CE", "WA", "partial", "RE", "MLE", "TLE", "slow", "JE")
FAIL_NAME = {"no code": "无代码", "CE": "编译错误", "WA": "答案错误", "partial": "部分分", "RE": "运行错误", "MLE": "超内存",
             "TLE": "超时", "slow": "只在官方时限下超时", "JE": "判题错误"}


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def geo(xs):
    xs = [x for x in xs if x and x > 0]
    return math.exp(statistics.mean(map(math.log, xs))) if xs else None


def failure(r):
    """The main reason an answer is not solved (lenient), or "slow" if it is solved but not under the official limit."""
    if r["solved"]:
        return None if r["strict_solved"] else "slow"
    v = r.get("verdicts") or {}
    if "no code" in v:
        return "no code"
    if "CE" in v:
        return "CE"
    for k in ("WA", "RE", "MLE", "TLE", "JE"):
        if v.get(k):
            return k
    return "partial"


def load(run_dir, prices=None):
    info = json.load(open(os.path.join(run_dir, "run.json")))
    judged = {r["q"]: r for r in jl(os.path.join(run_dir, "judge.jsonl"))}
    last = {}
    for r in jl(os.path.join(run_dir, "answers.jsonl")):
        last[r["q"]] = r
    # samples the API never answered (retries used up, out of balance): not the model's failure, left out of every
    # rate and counted separately
    unanswered = sorted(q for q, r in last.items() if r.get("finish") == "error")
    judged = {q: r for q, r in judged.items() if q not in unanswered}
    perf = {r["q"]: r for r in jl(os.path.join(run_dir, "perf.jsonl"))}
    quality = {r["q"]: r for r in jl(os.path.join(run_dir, "quality.jsonl"))}
    complexity = {r["q"]: r for r in jl(os.path.join(run_dir, "complexity.jsonl"))}
    calls = jl(os.path.join(run_dir, "usage.jsonl"))
    metas = {r["pid"]: L.load_meta(r["pid"]) for r in judged.values()}
    return {"dir": run_dir, "model": info["model"], "info": info, "judged": judged, "perf": perf, "quality": quality,
            "complexity": complexity, "unanswered": unanswered,
            "calls": calls, "metas": metas, "prices": prices}


def tier_stats(rs, metas, perf):
    by_pid = collections.defaultdict(list)
    for r in rs:
        by_pid[r["pid"]].append(r)
    fails = collections.Counter(failure(r) for r in rs)
    fails.pop(None, None)
    ratios = [perf[r["q"]]["ratio"] for r in rs if r["q"] in perf]
    mem = []
    for r in rs:
        ref = (metas[r["pid"]].get("ref") or {}).get(metas[r["pid"]]["lang"])
        if r["solved"] and ref and ref.get("rss_kb"):
            mem.append(r["max_rss_kb"] / ref["rss_kb"])
    n = len(rs)
    return {"problems": len(by_pid), "samples": n,
            "pass1": 100 * sum(r["solved"] for r in rs) / n if n else None,
            "pass1_strict": 100 * sum(r["strict_solved"] for r in rs) / n if n else None,
            "score": statistics.mean(r["score"] for r in rs) if n else None,
            "score_strict": statistics.mean(r["strict_score"] for r in rs) if n else None,
            "passn": 100 * sum(any(x["solved"] for x in v) for v in by_pid.values()) / len(by_pid) if by_pid else None,
            "n_per_problem": max((len(v) for v in by_pid.values()), default=0),
            "fails": dict(fails), "perf_n": len(ratios), "perf_geo": geo(ratios),
            "perf_faster": sum(x <= 1.0 for x in ratios), "perf_2x": sum(x >= 2 for x in ratios),
            "mem_geo": geo(mem)}


def usage_stats(run, tier_of):
    calls = run["calls"]
    ok = [c for c in calls if "error" not in c]
    out = {"calls": len(calls), "errors": len(calls) - len(ok)}
    tok = [U.tokens(c.get("usage")) for c in ok]
    out.update(prompt=sum(t[0] for t in tok), completion=sum(t[2] for t in tok), reasoning=sum(t[3] for t in tok))
    lat = [c["end"] - c["start"] for c in ok]
    ttft = [c["first_token"] - c["start"] for c in ok if c.get("first_token")]
    out["latency"] = U.stats(lat)
    out["ttft"] = U.stats(ttft)
    out["span_h"] = (max(c["end"] for c in calls) - min(c["start"] for c in calls)) / 3600 if calls else 0
    per_tier = collections.defaultdict(lambda: {"completion": 0, "calls": 0, "cost": 0.0})
    for c in ok:
        t = tier_of.get(c["q"].split("#")[0])
        per_tier[t]["completion"] += U.tokens(c.get("usage"))[2]
        per_tier[t]["calls"] += 1
        if run["prices"]:
            per_tier[t]["cost"] += U.call_cost(c, run["prices"])
    out["per_tier"] = dict(per_tier)
    out["cost"] = sum(U.call_cost(c, run["prices"]) for c in calls) if run["prices"] else None
    return out


def quality_stats(run):
    rows = list(run["quality"].values())
    out = {}
    for name, sel in (("all", rows), ("correct", [r for r in rows if r.get("solved")])):
        ok = [r for r in sel if r.get("pylint") and r.get("radon")]
        if not ok:
            out[name] = None
            continue
        m = lambda f: statistics.mean(f(r) for r in ok)  # noqa: E731
        sl = sum(r["radon"]["sloc"] for r in ok) or 1
        out[name] = {"n": len(ok), "pylint_issues": m(lambda r: r["pylint"]["total"]),
                     "pylint_score": statistics.mean(r["pylint"]["score"] for r in ok if r["pylint"]["score"] is not None),
                     "cc": m(lambda r: r["radon"]["complexity"]), "mi": m(lambda r: r["radon"]["mi"]),
                     "sloc": m(lambda r: r["radon"]["sloc"]),
                     "issues_per_100sloc": 100 * sum(r["pylint"]["total"] for r in ok) / sl,
                     **{f"sonar_{q}": (statistics.mean(r["sonar"][q] for r in ok) if all(r.get("sonar") for r in ok) else None)
                        for q in ("maintainability", "reliability", "security")}}
    return out


def complexity_stats(run):
    """Per tier and kind (time, space): answers per class and the median growth exponent k relative to the
    official solution (see tools/ladder_complexity.py), plus the answers that grow more slowly (for review)."""
    out = {}
    for t in L.TIERS:
        rows = [r for r in run["complexity"].values() if r["tier"] == t]
        if not rows:
            continue
        d = {}
        for kind in ("time", "space"):
            ks = [r[kind]["k"] for r in rows if r[kind].get("class") in ("better", "same", "worse")]
            d[kind] = {"classes": dict(collections.Counter(r[kind]["class"] for r in rows)),
                       "k_median": statistics.median(ks) if ks else None,
                       "better": sorted(r["q"] for r in rows if r[kind]["class"] == "better")}
        out[t] = d
    return out


def analyze(run):
    rs = list(run["judged"].values())
    metas = run["metas"]
    s = {"model": run["model"], "tiers": {}, "subsets": {}, "unanswered": run.get("unanswered", [])}
    for t in L.TIERS:
        sel = [r for r in rs if r["tier"] == t]
        if sel:
            s["tiers"][t] = tier_stats(sel, metas, run["perf"])
    for t in ("L3", "L4"):
        for sub in sorted({r["subset"] for r in rs if r["tier"] == t}):
            sel = [r for r in rs if r["tier"] == t and r["subset"] == sub]
            s["subsets"][f"{t}|{sub}"] = tier_stats(sel, metas, run["perf"])
    s["complexity"] = complexity_stats(run)
    s["usage"] = usage_stats(run, {p: m["tier"] for p, m in metas.items()})
    s["quality"] = quality_stats(run)
    s["per_problem"] = {}
    for pid in sorted(metas):
        v = [r for r in rs if r["pid"] == pid]
        s["per_problem"][pid] = {"tier": metas[pid]["tier"], "title": metas[pid]["title"], "subset": metas[pid]["subset"],
                                 "solved": sum(r["solved"] for r in v), "n": len(v),
                                 "score": statistics.mean(r["score"] for r in v),
                                 "fail": collections.Counter(failure(r) for r in v if failure(r)).most_common(1)[0][0]
                                 if any(failure(r) for r in v) else None}
    return s


# ---------------------------------------------------------------- rendering

def f1(x, nd=1, suffix=""):
    return "–" if x is None else f"{x:.{nd}f}{suffix}"


def tex(s):
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
            .replace("#", r"\#").replace("$", r"\$"))


# ---------------------------------------------------------------- dimensions and scoring rules (both formats)

CRITERIA = [  # (dimension, metric, how it is computed, direction)
    ("正确性", "测试点得分 $s_t$",
     "每个测试点 0–1：USACO 忽略空白逐 token 比对，相同为 1、否则 0；EGOI、IOI 取官方 checker 给出的 0–1 分；"
     "FrontierCS 取官方 checker 输出的 Ratio（达到参考解为 0.6，超过参考解按对数加分，最高 1）。"
     "程序编译失败、运行出错、超时或超内存，该测试点为 0。", ""),
    ("正确性", "题目得分 $S$（0–100）",
     "USACO：$S = 100 \\cdot \\frac{1}{T}\\sum_t s_t$（每个测试点等分）；EGOI、IOI：$S = 100 \\cdot \\frac{\\sum_g w_g \\min_{t \\in g} s_t}{\\sum_g w_g}$"
     "（子任务 $g$ 取其中测试点的最低分，再乘以子任务分值 $w_g$）；FrontierCS：$S = 100 \\cdot \\frac{1}{T}\\sum_t \\mathrm{Ratio}_t$。", "↑"),
    ("正确性", "解出", "所有测试点 $s_t = 1$。", ""),
    ("正确性", "pass@1、平均得分、pass@$n$",
     "pass@1 = 解出的采样数 ÷ 采样总数 × 100；平均得分 = 所有采样的 $S$ 的平均；pass@$n$ = 至少一次采样解出的题数 ÷ 题数 × 100。"
     "每档采样次数：L1、L2、L5 各 1 次，L3、L4 各 3 次，temperature 0.2。", "↑"),
    ("正确性 / 效率", "宽时限与官方时限",
     "每个测试点只运行一次，时限为官方时限的 5 倍（宽时限）。宽时限口径：按上面的规则计分。官方时限口径：CPU 时间超过官方时限的测试点记 0，"
     "再按同样的规则算 $S$、pass@1。前者回答“算法对不对”，后者回答“是否和人类选手一样在时限内通过”。", "↑"),
    ("效率", "运行时间倍数",
     "只对解出的答案、且官方解在某个测试点上至少需要 0.05 秒 CPU 的题：取官方解最慢的 3 个测试点，答案与官方解交替各运行 3 次取中位数，"
     "$r$ = 答案 CPU 时间 ÷ 官方解 CPU 时间（取官方解最慢的那个测试点）；各档报告 $r$ 的几何平均和题数。同语言比较。", "↓"),
    ("效率", "内存倍数", "解出的答案在所有测试点上的峰值内存 ÷ 官方解的峰值内存，各档取几何平均。", "↓"),
    ("复杂度", "相对官方解的增长幂次 $k$",
     "官方测试不是按规模排列的序列（USACO 里耗时较长的测试点大多都是最大规模），所以以官方解自己的工作量为横轴：在官方解至少需要 2 ms CPU"
     "（扣除空程序）的测试点上（最多 20 个，均匀覆盖其耗时范围），答案与官方解交替各运行 5 次取中位数，拟合 "
     "$\\log y_{\\text{答案}} = a + k \\log y_{\\text{官方}}$。若官方解为 $\\Theta(f(n))$、答案为 $\\Theta(f(n)^k)$，$k$ 即该指数。"
     "$R^2 \\ge 0.8$ 时：$k \\le 0.75$ 且在官方解最重的 3 个测试点上答案至少快 2 倍为更优（列出供人工复核），$0.75 < k < 1.33$ 为同阶，"
     "$k \\ge 1.33$ 且在这些测试点上至少慢 2 倍为更差；$R^2 < 0.8$，或斜率与最重测试点上的快慢对不上（某一方有固定开销会把斜率拉偏），为不确定；"
     "可用测试点少于 4 个或官方耗时跨度不足 4 倍为不可测。空间同理（峰值内存，至少高于空程序 1 MB）。"
     "这些测试点的输入大小跨度达到 8 倍时，另报两者按输入大小的增长幂次。", ""),
    ("失败类型", "每份未解出答案的主要原因",
     "按顺序取第一个成立的：无代码、编译错误、答案错误、运行错误、超内存、超时、部分分（部分测试点得分）；"
     "宽时限下解出但官方时限下没有全部通过的记为“只在官方时限下超时”。", ""),
    ("静态质量", "Pylint、Radon、SonarQube（只限 L1–L2 的 Python 答案）",
     "按 arXiv:2610.19167 的口径与版本：Pylint 3.3.5 默认配置的问题数（C/R/W/E）与 0–10 分，Radon 6.0.1 的圈复杂度（所有条目之和）、"
     "可维护性指数 MI、SLOC，SonarQube 10.4 的可维护性/可靠性/安全问题数；报告正确答案的每份平均与每百行 SLOC 的问题数。", "见表头"),
    ("成本与时延", "token、费用、延迟、首个 token 时间",
     "费用 = (输入 − 缓存命中) × 输入单价 + 缓存命中 × 命中单价 + 输出（含思考）× 输出单价，单价按每百万 token，分时计价按每次调用的开始时间；"
     "延迟为每次调用从发出到收完的时间。", "↓"),
    ("泄露检查", "2026 子集与 USACO 子集",
     "L3、L4 中 EGOI/IOI 2026 新题与同档 USACO 旧题分开报告 pass@1 与平均得分；新题明显更差时提示旧题可能见过。只作提示，不作结论。", ""),
]
NO_TOTAL = "各维度分开报告，不合成总分；表格中 ↑ 越大越好，↓ 越小越好，没有箭头的只作描述。"


def md_math(x):
    import re
    return re.sub(r"\\text\{([^}]*)\}", r"\1", x).replace("$", "")


def criteria_md():
    L_ = ["## 评测维度与打分标准", "", NO_TOTAL, "", "| 维度 | 指标 | 计算方法 | 方向 |", "|---|---|---|---|"]
    for d, m, how, arrow in CRITERIA:
        L_.append(f"| {d} | {md_math(m)} | {md_math(how)} | {arrow} |")
    return L_ + [""]


def criteria_tex():
    rows = [r"\section{评测维度与打分标准}", NO_TOTAL,
            r"{\small\begin{longtable}{@{}p{1.6cm}p{2.6cm}p{10.3cm}p{0.9cm}@{}}", r"\toprule 维度 & 指标 & 计算方法 & 方向 \\ \midrule \endhead"]
    rows += [f"{d} & {m} & {how} & {arrow} \\\\" for d, m, how, arrow in CRITERIA]
    rows += [r"\bottomrule", r"\end{longtable}}"]
    return "\n".join(rows)


def md_report(stats, date):
    models = [s["model"] for s in stats]
    L_ = [f"# 阶梯代码评测报告（{date}）", ""] + criteria_md()
    for s in stats:
        if s["unanswered"]:
            L_ += [f"- {s['model']}：{len(s['unanswered'])} 个采样因接口错误（重试用完或余额不足）没有拿到回答，不计入任何比率："
                   + "、".join(s["unanswered"]), ""]
    L_ += ["## 各档正确率", "", "| 档位 | 指标 | " + " | ".join(models) + " |", "|---|---|" + "---:|" * len(models)]
    for t in L.TIERS:
        if not any(t in s["tiers"] for s in stats):
            continue
        for key, name in (("pass1", "pass@1（宽时限）↑"), ("pass1_strict", "pass@1（官方时限）↑"),
                          ("score", "平均得分（宽时限）↑"), ("score_strict", "平均得分（官方时限）↑"), ("passn", "pass@n ↑")):
            vals = [f1(s["tiers"].get(t, {}).get(key)) for s in stats]
            L_.append(f"| {TIER_NAME[t]} | {name} | " + " | ".join(vals) + " |")
    L_ += ["", "## 2026 新题与 USACO 对照（泄露检查）", ""]
    if not any(k.endswith("|2026") for s in stats for k in s["subsets"]):
        L_ += ["本次评测还没有 2026 年的 EGOI/IOI 题，下表只是 USACO 两个赛季之间的对照（2025-26 赛季的题更新）。", ""]
    L_ += ["| 档位 / 子集 | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
    keys = sorted({k for s in stats for k in s["subsets"]})
    for k in keys:
        L_.append(f"| {k.replace('|', ' / ')}（pass@1 / 得分）↑ | " + " | ".join(
            f"{f1(s['subsets'].get(k, {}).get('pass1'))} / {f1(s['subsets'].get(k, {}).get('score'))}" for s in stats) + " |")
    L_ += ["", "## 代码性能（相对官方解，同语言）", "", "| 档位 | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
    for t in L.TIERS:
        if any(s["tiers"].get(t, {}).get("perf_n") for s in stats):
            L_.append(f"| {TIER_NAME[t]}：CPU 时间倍数（几何平均）↓ | " + " | ".join(
                f"{f1(s['tiers'].get(t, {}).get('perf_geo'), 2, '×')}（{s['tiers'].get(t, {}).get('perf_n', 0)} 份答案）" for s in stats) + " |")
    L_ += ["", "## 时间与空间复杂度（相对官方解，同一批官方测试）", "",
           "k = 答案耗时（或内存）相对官方解耗时（或内存）的增长幂次：k ≤ 0.75 且在官方解最重的测试点上至少快 2 倍为更优（可能是更好或更新颖的解法），"
           "0.75 < k < 1.33 同阶，k ≥ 1.33 且至少慢 2 倍为更差；其余为不确定。方法见上表“复杂度”一行。", "",
           "| 档位 | 维度 | " + " | ".join(models) + " |", "|---|---|" + "---:|" * len(models)]
    for t in L.TIERS:
        for kind, kname in (("time", "时间"), ("space", "空间")):
            if not any(s["complexity"].get(t) for s in stats):
                continue
            def cell(s):
                c = (s["complexity"].get(t) or {}).get(kind)
                if not c:
                    return "–"
                k = c["classes"]
                return " / ".join(f"{name} {k.get(key, 0)}" for key, name in (('better', '更优'), ('same', '同阶'), ('worse', '更差'), ('uncertain', '不确定'), ('not measurable', '不可测'), ('no reference', '无官方解'))) + f"；k 中位数 {f1(c['k_median'], 2)}"
            L_.append(f"| {TIER_NAME[t]} | {kname} | " + " | ".join(cell(s) for s in stats) + " |")
    nov = [(s["model"], t, kind, q) for s in stats for t, d in s["complexity"].items() for kind in ("time", "space")
           for q in d[kind]["better"]]
    L_ += [""] + ([f"- 增长慢于官方解、值得人工复核的答案：" + "；".join(f"{m} {q}（{'时间' if k == 'time' else '空间'}）"
                                                        for m, t, k, q in nov)] if nov else ["- 没有增长慢于官方解的答案。"])
    L_ += ["", "## 失败类型（答案数）", ""]
    for s in stats:
        L_.append(f"- {s['model']}：" + "；".join(f"{TIER_NAME[t]} " + "，".join(f"{FAIL_NAME[k]} {v}" for k, v in sorted(
            st["fails"].items(), key=lambda kv: FAIL_ORDER.index(kv[0]))) for t, st in s["tiers"].items() if st["fails"]))
    L_ += ["", "## 静态质量（L1–L2 Python，正确答案）", "", "| 指标 | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
    for key, name in (("pylint_issues", "Pylint 问题数 ↓"), ("pylint_score", "Pylint 分 ↑"), ("cc", "圈复杂度 CC ↓"),
                      ("mi", "可维护性 MI ↑"), ("sloc", "SLOC"), ("issues_per_100sloc", "每百行问题数 ↓"),
                      ("sonar_maintainability", "SonarQube 可维护性问题 ↓"), ("sonar_reliability", "SonarQube 可靠性问题 ↓"),
                      ("sonar_security", "SonarQube 安全问题 ↓")):
        L_.append(f"| {name} | " + " | ".join(f1((s["quality"].get("correct") or {}).get(key), 2) for s in stats) + " |")
    L_ += ["", "## 用量与费用", "", "| 指标 | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
    L_.append("| 调用数（出错） | " + " | ".join(f"{s['usage']['calls']}（{s['usage']['errors']}）" for s in stats) + " |")
    L_.append("| 输出 token ↓ | " + " | ".join(U.fmt_tok(s["usage"]["completion"]) for s in stats) + " |")
    L_.append("| 延迟中位数 ↓ | " + " | ".join(f1((s["usage"]["latency"] or {}).get("median"), 0, " s") for s in stats) + " |")
    L_.append("| 费用 ↓ | " + " | ".join("–" if s["usage"]["cost"] is None else f"${s['usage']['cost']:.2f}" for s in stats) + " |")
    L_ += ["", "## 逐题结果", ""]
    for s in stats:
        L_ += [f"### {s['model']}", "", "| 题目 | 档 | 子集 | 解出 / 采样 | 平均得分 | 主要失败 |", "|---|---|---|---:|---:|---|"]
        for pid, p in s["per_problem"].items():
            L_.append(f"| {pid} {p['title']} | {p['tier']} | {p['subset']} | {p['solved']}/{p['n']} | {p['score']:.1f} | {FAIL_NAME.get(p['fail'], '')} |")
        L_.append("")
    return "\n".join(L_) + "\n"


PREAMBLE = r"""\documentclass[11pt,a4paper,fontset=none]{ctexart}
\usepackage[margin=2.2cm]{geometry}
\usepackage{fontspec}
\IfFontExistsTF{Times New Roman}{\setmainfont{Times New Roman}\setsansfont{Times New Roman}}{\setmainfont{TeX Gyre Termes}\setsansfont{TeX Gyre Termes}}
\newcommand{\KaiPath}{/System/Library/AssetsV2/com_apple_MobileAsset_Font8/88d6cc32a907955efa1d014207889413890573be.asset/AssetData/}
\IfFileExists{\KaiPath Kaiti.ttc}{%
  \setCJKmainfont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0, BoldFont=Kaiti.ttc, BoldFeatures={FontIndex=3}]
  \setCJKsansfont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0, BoldFont=Kaiti.ttc, BoldFeatures={FontIndex=3}]
  \setCJKmonofont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0]}{%
  \IfFontExistsTF{Kaiti SC}{\setCJKmainfont{Kaiti SC}\setCJKsansfont{Kaiti SC}\setCJKmonofont{Kaiti SC}}{%
  \setCJKmainfont{FandolKai}\setCJKsansfont{FandolKai}\setCJKmonofont{FandolKai}}}
\usepackage{amsmath}
\usepackage{booktabs,tabularx,longtable,array}
\usepackage{enumitem}
\usepackage{xurl}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\setlist{nosep,leftmargin=1.4em}
\ctexset{section={format=\Large\bfseries\raggedright},subsection={format=\large\bfseries\raggedright}}
\setlength{\parskip}{0.3em}
\renewcommand{\arraystretch}{1.15}
\pagestyle{fancy}\fancyhf{}
\lhead{\small BAI AI Lab 阶梯代码评测}\rhead{\small __DATE__}\cfoot{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}
"""


def tex_table(header, rows, spec):
    out = [r"\begin{center}\small", rf"\begin{{tabular}}{{{spec}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    out += [" & ".join(r) + r" \\" for r in rows]
    out += [r"\bottomrule", r"\end{tabular}", r"\end{center}"]
    return "\n".join(out)


def tex_report(stats, date):
    models = [tex(s["model"]) for s in stats]
    spec = "l" + "r" * len(models)
    parts = [PREAMBLE.replace("__DATE__", date), r"\begin{document}", r"\begin{center}",
             r"{\LARGE\bfseries 阶梯代码评测报告}\\[0.4em]", rf"{{\large {' / '.join(models)}}}\\[0.3em]",
             rf"{{\small {date} \quad L1--L4：USACO 2024--26 与 EGOI/IOI 2026；L5：FrontierCS 算法赛道}}",
             r"\end{center}"]
    parts.append(criteria_tex())
    for s in stats:
        if s["unanswered"]:
            parts.append(f"{tex(s['model'])}：{len(s['unanswered'])} 个采样因接口错误（重试用完或余额不足）没有拿到回答，不计入任何比率："
                         + "、".join(tex(q) for q in s["unanswered"]) + "。")
    parts.append(r"\section{各档正确率}")
    rows = []
    for t in L.TIERS:
        if not any(t in s["tiers"] for s in stats):
            continue
        for key, name in (("pass1", "pass@1 宽时限 ↑"), ("pass1_strict", "pass@1 官方时限 ↑"), ("score", "得分 宽时限 ↑"),
                          ("score_strict", "得分 官方时限 ↑")):
            rows.append([f"{TIER_NAME[t]}：{name}"] + [f1(s["tiers"].get(t, {}).get(key)) for s in stats])
        if any(s["tiers"].get(t, {}).get("n_per_problem", 1) > 1 for s in stats):
            rows.append([f"{TIER_NAME[t]}：pass@n ↑"] + [f1(s["tiers"].get(t, {}).get("passn")) for s in stats])
    parts.append(tex_table(["档位与指标"] + models, rows, spec))
    if any(s["subsets"] for s in stats):
        parts.append(r"\section{2026 新题与 USACO 对照}")
        parts.append("同一档内，2026 年的新题（EGOI、IOI）与 USACO 旧题的 pass@1 / 平均得分。新题明显更低而难度相当时，旧题成绩可能受训练数据泄露抬高。")
        if not any(k.endswith("|2026") for s in stats for k in s["subsets"]):
            parts.append("本次评测还没有 2026 年的 EGOI/IOI 题，下表只是 USACO 两个赛季之间的对照（2025--26 赛季的题更新）。")
        keys = sorted({k for s in stats for k in s["subsets"]})
        parts.append(tex_table(["档位 / 子集"] + models, [[tex(k.replace("|", " / "))] + [
            f"{f1(s['subsets'].get(k, {}).get('pass1'))} / {f1(s['subsets'].get(k, {}).get('score'))}" for s in stats] for k in keys], spec))
    prow = [[f"{TIER_NAME[t]} ↓"] + [f"{f1(s['tiers'].get(t, {}).get('perf_geo'), 2, '×')} ({s['tiers'].get(t, {}).get('perf_n', 0)})"
                                      for s in stats] for t in L.TIERS if any(s["tiers"].get(t, {}).get("perf_n") for s in stats)]
    if prow:
        parts.append(r"\section{代码性能}")
        parts.append("解出的答案在官方解最慢的 3 个测试点上与官方解交替各跑 3 次取中位数；表中为答案 CPU 时间 ÷ 官方解（几何平均，括号内为答案份数）。")
        parts.append(tex_table(["档位"] + models, prow, spec))
    if any(s["complexity"] for s in stats):
        parts.append(r"\section{时间与空间复杂度}")
        parts.append("$k$ 为答案耗时（或内存）相对官方解的增长幂次：$k \\le 0.75$ 且在官方解最重的测试点上至少快 2 倍为更优（可能是更好或更新颖的解法），"
                     "$0.75 < k < 1.33$ 同阶，$k \\ge 1.33$ 且至少慢 2 倍为更差，其余为不确定；方法见“评测维度与打分标准”。")
        crow = []
        for t in L.TIERS:
            for kind, kname in (("time", "时间"), ("space", "空间")):
                if not any((s["complexity"].get(t) or {}).get(kind) for s in stats):
                    continue
                def c2(s):
                    c = (s["complexity"].get(t) or {}).get(kind)
                    if not c:
                        return "–"
                    k = c["classes"]
                    return "/".join(str(k.get(key, 0)) for key, _ in (('better', '更优'), ('same', '同阶'), ('worse', '更差'), ('uncertain', '不确定'), ('not measurable', '不可测'), ('no reference', '无官方解'))) + f"，k={f1(c['k_median'], 2)}"
                crow.append([f"{TIER_NAME[t]}：{kname}（更优/同阶/更差/不确定/不可测/无官方解）"] + [c2(s) for s in stats])
        parts.append(tex_table(["档位"] + models, crow, spec))
        nov = [(s["model"], q, k) for s in stats for t, d in s["complexity"].items() for k in ("time", "space") for q in d[k]["better"]]
        parts.append(("增长慢于官方解、值得人工复核的答案：" + "；".join(f"{tex(m)} {tex(q)}（{'时间' if k == 'time' else '空间'}）"
                                                         for m, q, k in nov) + "。") if nov else "没有增长慢于官方解的答案。")
    parts.append(r"\section{失败类型}")
    frows = []
    for t in L.TIERS:
        for k in FAIL_ORDER:
            vals = [str(s["tiers"].get(t, {}).get("fails", {}).get(k, 0)) for s in stats]
            if any(v != "0" for v in vals):
                frows.append([f"{TIER_NAME[t]}：{FAIL_NAME[k]}"] + vals)
    parts.append(tex_table(["档位与类型"] + models, frows or [["无"] + [""] * len(models)], spec))
    if any(s["quality"].get("correct") for s in stats):
        parts.append(r"\section{静态质量（L1--L2，Python）}")
        qrows = [[name] + [f1((s["quality"].get("correct") or {}).get(key), 2) for s in stats] for key, name in (
            ("pylint_issues", "Pylint 问题数 ↓"), ("pylint_score", "Pylint 分 ↑"), ("cc", "圈复杂度 CC ↓"), ("mi", "可维护性 MI ↑"),
            ("sloc", "SLOC"), ("issues_per_100sloc", "每百行问题数 ↓"), ("sonar_maintainability", "SonarQube 可维护性 ↓"),
            ("sonar_reliability", "SonarQube 可靠性 ↓"), ("sonar_security", "SonarQube 安全 ↓"))]
        parts.append(tex_table(["指标（正确答案）"] + models, qrows, spec))
    parts.append(r"\section{用量与费用}")
    urows = [["调用（出错）"] + [f"{s['usage']['calls']} ({s['usage']['errors']})" for s in stats],
             ["输出 token ↓"] + [U.fmt_tok(s["usage"]["completion"]) for s in stats],
             ["延迟中位数 ↓"] + [f1((s["usage"]["latency"] or {}).get("median"), 0, " s") for s in stats],
             ["费用 ↓"] + ["–" if s["usage"]["cost"] is None else f"\\${s['usage']['cost']:.2f}" for s in stats]]
    parts.append(tex_table(["指标"] + models, urows, spec))
    parts.append(r"\section{逐题结果}")
    for s in stats:
        parts.append(rf"\subsection*{{{tex(s['model'])}}}")
        parts += [r"{\small\begin{longtable}{llrrl}", r"\toprule 题目 & 档 & 解出/采样 & 得分 & 主要失败 \\ \midrule \endhead"]
        parts += [rf"{tex(pid)} {tex(p['title'])} & {p['tier']} & {p['solved']}/{p['n']} & {p['score']:.1f} & {tex(FAIL_NAME.get(p['fail'], ''))} \\"
                  for pid, p in s["per_problem"].items()]
        parts += [r"\bottomrule", r"\end{longtable}}"]
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--prices", default="", help="model=in,hit,out;model2=... (per 1M tokens)")
    a = ap.parse_args()
    per = {}
    for x in filter(None, a.prices.split(";")):
        m, v = x.split("=")
        i, h, o = map(float, v.split(","))
        per[m] = {"in": i, "hit": h, "out": o}
    env = None
    if os.environ.get("PRICE_IN") and os.environ.get("PRICE_OUT"):
        env = {"in": float(os.environ["PRICE_IN"]), "hit": float(os.environ.get("PRICE_HIT") or os.environ["PRICE_IN"]),
               "out": float(os.environ["PRICE_OUT"])}
        if os.environ.get("PRICE_OFF_IN") and os.environ.get("PRICE_OFF_OUT"):  # off-peak rates, as cb usage
            env["off"] = {"in": float(os.environ["PRICE_OFF_IN"]), "out": float(os.environ["PRICE_OFF_OUT"]),
                          "hit": float(os.environ.get("PRICE_OFF_HIT") or os.environ["PRICE_OFF_IN"])}
            env["peak_hours"] = [tuple(map(int, r.split("-"))) for r in os.environ.get("PEAK_HOURS_UTC", "1-4,6-10").split(",") if r]
    stats = []
    for d in a.runs:
        run = load(d)
        run["prices"] = per.get(run["model"], env)
        stats.append(analyze(run))
    os.makedirs(a.out, exist_ok=True)
    json.dump(stats, open(os.path.join(a.out, "report.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(a.out, "report.md"), "w").write(md_report(stats, a.date))
    open(os.path.join(a.out, "main.tex"), "w").write(tex_report(stats, a.date))
    open(os.path.join(a.out, "build.sh"), "w").write("#!/bin/bash\n# PDF of this report (xelatex with ctex; Times New Roman + Kaiti on the Mac)\n"
                                                    "cd \"$(dirname \"$0\")\" && xelatex -interaction=nonstopmode main.tex >/dev/null && "
                                                    "xelatex -interaction=nonstopmode main.tex >/dev/null && echo \"$(pwd)/main.pdf\"\n")
    print(f"report: {a.out}/report.md")
    if shutil.which("xelatex"):
        p = subprocess.run(["bash", os.path.join(a.out, "build.sh")], capture_output=True, text=True)
        print(p.stdout.strip() or "xelatex failed: see main.log")
    else:
        print(f"no xelatex here: copy {a.out} to a machine with xelatex and run bash build.sh")


if __name__ == "__main__":
    main()
