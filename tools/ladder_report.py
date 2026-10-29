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
import re
import shutil
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402
import lcb_usage as U  # noqa: E402

TIER_NAME = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式"}
FAIL_ORDER = ("no code", "timeout", "CE", "WA", "partial", "RE", "MLE", "TLE", "slow", "JE")
FAIL_NAME = {"no code": "无代码", "timeout": "生成超时", "CE": "编译错误", "WA": "答案错误", "partial": "部分分", "RE": "运行错误", "MLE": "超内存",
             "TLE": "超时", "slow": "只在官方时限下超时", "JE": "判题错误"}


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def geo(xs):
    xs = [x for x in xs if x and x > 0]
    return math.exp(statistics.mean(map(math.log, xs))) if xs else None


def failure(r, continuous=False):
    """The main reason an answer is not solved (lenient), or "slow" if it is solved but not under the official limit.
    On a continuously scored problem (FrontierCS) any score above 0 is "partial"; only a 0 gets a reason."""
    if continuous and not r["solved"] and r["score"] > 0:
        return "partial"
    if r["solved"]:
        return None if r["strict_solved"] else "slow"
    v = r.get("verdicts") or {}
    if "no code" in v:
        return "no code"
    if "timeout" in v:
        return "timeout"
    if "CE" in v:
        return "CE"
    for k in ("WA", "RE", "MLE", "TLE", "JE"):
        if v.get(k):
            return k
    return "partial"


def load(run_dir, prices=None, names=None):
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
    # the run's sample list, to tell a partial run (paused, not finished, judge not run yet) from a complete one
    pj = os.path.join(run_dir, "problems.json")
    planned = {p["q"]: p["difficulty"] for p in json.load(open(pj))} if os.path.exists(pj) else {}
    # problems taken out of the problem list after the run (found not judgeable): their answers are left out, listed
    man = info.get("manifest")
    dropped = []
    if man and os.path.exists(man):
        listed = {p for v in json.load(open(man))["tiers"].values() for p in v}
        dropped = sorted({r["pid"] for r in last.values()} - listed)
        judged = {q: r for q, r in judged.items() if r["pid"] in listed}
        planned = {q: t for q, t in planned.items() if q.split("#")[0] in listed}
        unanswered = [q for q in unanswered if q.split("#")[0] in listed]
    metas = {r["pid"]: L.load_meta(r["pid"]) for r in judged.values()}
    # samples cut for running over the per-request time limit: the length of each cut call in minutes, whether the
    # server dropped it (LADDER_CUT_IS_TIMEOUT) rather than our limit, and how the sample ended (a re-ask with a longer
    # limit, LADDER_REDO_TIMEOUTS, may have finished it)
    cut = collections.defaultdict(list)
    for c in calls:
        if "timeout" in (c.get("finish") or []):
            cut[c["q"]].append((round((c["end"] - c["start"]) / 60), "cut" in c))
    timeouts = {q: {"calls": v, "final": last[q].get("finish")} for q, v in cut.items()
                if q in last and q not in unanswered and q.split("#")[0] not in dropped}
    # the model's full name for the report (--names, else MODEL_NAME at generation time), the API id otherwise
    name = (names or {}).get(info["model"]) or info.get("name") or info["model"]
    return {"dir": run_dir, "model": info["model"], "name": name, "info": info, "judged": judged, "perf": perf, "quality": quality,
            "complexity": complexity, "unanswered": unanswered, "planned": planned, "dropped": dropped,
            "calls": calls, "metas": metas, "prices": prices, "timeouts": timeouts}


def tier_stats(rs, metas, perf):
    by_pid = collections.defaultdict(list)
    for r in rs:
        by_pid[r["pid"]].append(r)
    fails = collections.Counter(failure(r, metas[r["pid"]]["scoring"].get("type") == "mean") for r in rs)
    fails.pop(None, None)
    ratios = [perf[r["q"]]["ratio"] for r in rs if r["q"] in perf]
    mem = []
    for r in rs:
        ref = (metas[r["pid"]].get("ref") or {}).get(metas[r["pid"]]["lang"])
        if r["solved"] and ref and ref.get("rss_kb"):
            mem.append(r["max_rss_kb"] / ref["rss_kb"])
    n = len(rs)
    # FrontierCS scores 0-100 against a reference: no answer "solves" an open problem, so pass@k does not apply
    cont = bool(by_pid) and all(metas[p]["scoring"].get("type") == "mean" for p in by_pid)
    return {"problems": len(by_pid), "samples": n, "continuous": cont,
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
    out = {"calls": len(ok)}  # answered calls; retried transport errors are not part of the result
    tok = [U.tokens(c.get("usage")) for c in ok]
    out.update(prompt=sum(t[0] for t in tok), completion=sum(t[2] for t in tok), reasoning=sum(t[3] for t in tok))
    lat = [c["end"] - c["start"] for c in ok]
    ttft = [c["first_token"] - c["start"] for c in ok if c.get("first_token")]
    out["latency"] = U.stats(lat)
    out["ttft"] = U.stats(ttft)
    out["span_h"] = (max(c["end"] for c in calls) - min(c["start"] for c in calls)) / 3600 if calls else 0
    per_tier = collections.defaultdict(lambda: {"completion": 0, "calls": 0, "cost": 0.0, "lat": []})
    for c in ok:
        t = tier_of.get(c["q"].split("#")[0])  # None: a problem taken out of the list after the run
        per_tier[t]["completion"] += U.tokens(c.get("usage"))[2]
        per_tier[t]["calls"] += 1
        per_tier[t]["lat"].append(c["end"] - c["start"])
        if run["prices"]:
            per_tier[t]["cost"] += U.call_cost(c, run["prices"])
    for d in per_tier.values():
        d["latency_median"] = statistics.median(d.pop("lat")) if d["lat"] else None
    out["per_tier"] = dict(per_tier)
    out["cost"] = sum(U.call_cost(c, run["prices"]) for c in calls) if run["prices"] else None
    return out


def quality_stats(run):
    rows = list(run["quality"].values())
    out = {}
    groups = [("all", rows), ("correct", [r for r in rows if r.get("solved")])]
    groups += [(f"correct|{t}", [r for r in rows if r.get("solved") and r.get("tier") == t]) for t in L.TIERS]
    for name, sel in groups:
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
    s = {"model": run.get("name") or run["model"], "model_id": run["model"], "tiers": {}, "subsets": {}, "unanswered": run.get("unanswered", []),
         "dropped": run.get("dropped", []), "timeouts": run.get("timeouts", {})}
    for t in L.TIERS:
        sel = [r for r in rs if r["tier"] == t]
        if sel:
            s["tiers"][t] = tier_stats(sel, metas, run["perf"])
    for t in ("L3", "L4"):
        for sub in sorted({r["subset"] for r in rs if r["tier"] == t}):
            sel = [r for r in rs if r["tier"] == t and r["subset"] == sub]
            s["subsets"][f"{t}|{sub}"] = tier_stats(sel, metas, run["perf"])
    plan = collections.Counter(t for q, t in run.get("planned", {}).items() if q not in s["unanswered"])
    done = collections.Counter(r["tier"] for r in rs)
    s["pending"] = {t: [done[t], plan[t]] for t in L.TIERS if plan[t] > done[t]}  # tier: [judged, planned]
    s["complexity"] = complexity_stats(run)
    s["usage"] = usage_stats(run, {p: m["tier"] for p, m in metas.items()})
    s["quality"] = quality_stats(run)
    s["per_problem"] = {}
    for pid in sorted(metas):
        v = [r for r in rs if r["pid"] == pid]
        cont = metas[pid]["scoring"].get("type") == "mean"
        s["per_problem"][pid] = {"tier": metas[pid]["tier"], "title": metas[pid]["title"], "subset": metas[pid]["subset"],
                                 "continuous": metas[pid]["scoring"].get("type") == "mean",
                                 "solved": sum(r["solved"] for r in v), "n": len(v),
                                 "score": statistics.mean(r["score"] for r in v),
                                 "fail": collections.Counter(failure(r, cont) for r in v if failure(r, cont)).most_common(1)[0][0]
                                 if any(failure(r, cont) for r in v) else None}
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
     "宽时限下解出但官方时限下没有全部通过的记为“只在官方时限下超时”。单次生成超过时间上限的请求被切断，记为“生成超时”（视为没有通过；上限与重问见报告开头的说明）。FrontierCS 为连续分，得分大于 0 的答案记为部分分，只有 0 分的答案按上面的顺序找原因。", ""),
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
            r"{\small\begin{longtable}{@{}p{1.6cm}p{2.6cm}p{9.9cm}p{1.2cm}@{}}", r"\toprule 维度 & 指标 & 计算方法 & 方向 \\ \midrule \endhead"]
    rows += [f"{d} & {m} & {how} & {arrow} \\\\" for d, m, how, arrow in CRITERIA]
    rows += [r"\bottomrule", r"\end{longtable}}"]
    return "\n".join(rows)


NA = "不适用"
SUBSET_NAME = {"2026": "2026 新题（EGOI / IOI）"}
CPLX = (("better", "更优"), ("same", "同阶"), ("worse", "更差"), ("uncertain", "不确定"), ("not measurable", "不可测"),
        ("no reference", "无官方解"))


def table(head, rows, align, groups=None, tex_spec=None):
    """A table for both renderers: head = column names, groups = [(label, span), ...] over them (label "" = none),
    align = one l/r per column; tex_spec overrides the LaTeX column spec (e.g. wrapping p{} columns)."""
    return {"head": head, "rows": rows, "align": align, "groups": groups, "tex_spec": tex_spec}


def intro(stats, db):
    """First section: what each model is, what changed since its previous version, its highlights (samples/models.json)."""
    blocks = []
    for st in stats:
        m = db.get(st["model_id"])
        if not m:
            continue
        blocks.append(("h", m.get("name") or st["model"]))
        facts = [(k, m[f]) for k, f in (("厂商", "vendor"), ("发布", "released"), ("权重与许可", "weights"), ("架构", "architecture"),
                                         ("价格", "price"), ("本次调用", "access")) if m.get(f)]
        blocks.append(table(["项目", "内容"], [[k, v] for k, v in facts], "ll", tex_spec=r"@{}p{2.2cm}>{\raggedright\arraybackslash}p{13.6cm}@{}"))
        if m.get("updates"):
            blocks += ["相较上一版的更新：", ("ul", m["updates"])]
        if m.get("highlights"):
            blocks += ["亮点：", ("ul", m["highlights"])]
        if m.get("sources"):
            blocks.append(("links", m["sources"]))
    if not blocks:
        return []
    return [("模型简介", ["各模型的发布信息、相较上一版的更新与亮点，整理自厂商公告与模型卡；标注“厂商自报”的分数未经独立复现，"
                        "与本报告的测评结果不是同一口径。"] + blocks)]


def notes(stats):
    multi = len(stats) > 1
    out = []
    for s in stats:
        who = f"{s['model']}：" if multi else ""
        if s["unanswered"]:
            out.append(f"{who}{len(s['unanswered'])} 个采样因接口错误（重试用完或余额不足）没有拿到回答，不计入任何比率："
                       + "、".join(s["unanswered"]) + "。")
        if s["dropped"]:
            out.append(f"{who}{len(s['dropped'])} 道题在运行后从题单中剔除（当前判题程序无法正确评测），其答案不计入："
                       + "、".join(s["dropped"]) + "。")
        if s["pending"]:
            out.append(f"{who}部分结果，{sum(p - d for d, p in s['pending'].values())} 个采样还没有生成或判题，不计入任何比率"
                       "（已判 / 计划）：" + "，".join(f"{t} {d}/{p}" for t, (d, p) in s["pending"].items()) + "。")
        if s["timeouts"]:
            out.append(f"{who}" + timeout_note(s["timeouts"]))
    return out


def timeout_note(t):
    """How many samples were cut by the time limit, the limit, and what a re-ask with a longer limit made of them."""
    first = collections.Counter(v["calls"][0][0] for v in t.values() if not v["calls"][0][1])
    redone = {q: v for q, v in t.items() if len(v["calls"]) > 1 or v["final"] != "timeout"}
    later = [m for v in redone.values() for m, server in v["calls"][1:] if not server]
    ok = sum(v["final"] != "timeout" for v in redone.values())
    still = [v for v in redone.values() if v["final"] == "timeout"]
    by_server = sorted(v["calls"][-1][0] for v in still if v["calls"][-1][1])  # minutes at which the server dropped them
    txt = (f"{len(t)} 个采样单次生成超过 {first.most_common(1)[0][0] if first else '–'} 分钟被切断" if first
           else f"{len(t)} 个采样的生成被切断")
    if redone:
        txt += (f"，再以 {max(later)} 分钟为限重问一次" if later else "，再以更长的上限重问一次") + f"：{ok} 个在时限内完成，按正常答案判题"
        if still:
            span = by_server and (str(by_server[0]) if by_server[0] == by_server[-1] else f"{by_server[0]}–{by_server[-1]}")
            txt += f"；{len(still)} 个仍未完成" + (f"（其中 {len(by_server)} 个是服务端在约 {span} 分钟时主动断开）" if by_server else "")
            txt += "，记为“生成超时”"
    if not redone:
        txt += "，记为“生成超时”"
    elif len(t) > len(redone):
        txt += f"；{len(t) - len(redone)} 个未重问，记为“生成超时”"
    return txt + "。超时请求的输出 token 为按字数估算的值。"


def sign_test(wins, losses):
    """Two-sided exact sign test: the chance of a split at least this uneven between wins and losses if both models
    were equally good (ties left out)."""
    n = wins + losses
    if not n:
        return None
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n)


def f_p(p):
    return "–" if p is None else "< 0.001" if p < 0.001 else f"{p:.3f}"


def f_d(x, nd=1):
    """A difference, signed."""
    return "–" if x is None else f"{x:+.{nd}f}"


def comparison(stats):
    """The numbers of the head-to-head section, B (second run) against A (first run), for both the tables and the
    figures (ladder_figures.py)."""
    A, B = stats
    short = [s["model"].split()[0] for s in stats]
    if short[0] == short[1]:
        short = [s["model"] for s in stats]
    common = sorted(set(A["per_problem"]) & set(B["per_problem"]))
    tiers = [t for t in L.TIERS if t in A["tiers"] and t in B["tiers"]]
    discrete = [t for t in tiers if not A["tiers"][t]["continuous"]]
    pool = f"{discrete[0]}–{discrete[-1]} 合计" if discrete else None

    def pooled(s, ts):  # L1-L4 together: every sample counts once
        n = sum(s["tiers"][t]["samples"] for t in ts)
        w = lambda k: sum(s["tiers"][t][k] * s["tiers"][t]["samples"] for t in ts) / n  # noqa: E731
        return {"problems": sum(s["tiers"][t]["problems"] for t in ts), "samples": n, "continuous": False,
                "pass1": w("pass1"), "pass1_strict": w("pass1_strict"), "score": w("score")}

    rows_t = [(TIER_NAME[t], A["tiers"][t], B["tiers"][t]) for t in tiers]
    if len(discrete) > 1:
        rows_t.append((pool, pooled(A, discrete), pooled(B, discrete)))
    scores = [{"label": name, "continuous": x["continuous"], "problems": x["problems"],
               **{k: [None, None] if x["continuous"] and k != "score" else [x[k], y[k]] for k in ("pass1", "pass1_strict", "score")}}
              for name, x, y in rows_t]

    # per problem: who scores more on average (a difference under 0.05 is a tie), and who solves it at least once
    h2h = []
    for t in tiers + ["合计"]:
        pids = [p for p in common if t == "合计" or A["per_problem"][p]["tier"] == t]
        if not pids:
            continue
        wins, tie = [0, 0], 0
        solve = [0, 0, 0, 0]  # both, only A, only B, neither
        for pid in pids:
            pa, pb = A["per_problem"][pid], B["per_problem"][pid]
            d = pb["score"] - pa["score"]
            if abs(d) < 0.05:
                tie += 1
            else:
                wins[d > 0] += 1
            if not pa["continuous"]:
                sa, sb = pa["solved"] > 0, pb["solved"] > 0
                solve[0 if sa and sb else 1 if sa else 2 if sb else 3] += 1
        cont = t != "合计" and A["tiers"][t]["continuous"]
        h2h.append({"label": TIER_NAME.get(t, f"{tiers[0]}–{tiers[-1]} 合计"), "n": len(pids), "wins": wins, "tie": tie,
                    "p": sign_test(*wins), "solve": None if cont else solve})

    cost = []
    for t in tiers + ["合计"]:
        r = {"label": TIER_NAME.get(t, "合计"), "total": t == "合计", "tok": [], "lat": [], "cost": [], "per_solved": []}
        for s in stats:
            u = s["usage"]
            priced = u["cost"] is not None
            if t == "合计":
                d = {"calls": u["calls"], "completion": u["completion"], "latency_median": (u["latency"] or {}).get("median"), "cost": u["cost"]}
                solved = sum(s["tiers"][x]["pass1"] * s["tiers"][x]["samples"] / 100 for x in discrete)
                cost_solved = sum((u["per_tier"].get(x) or {}).get("cost", 0) for x in discrete)
            else:
                d = u["per_tier"].get(t) or {}
                solved = None if s["tiers"][t]["continuous"] else s["tiers"][t]["pass1"] * s["tiers"][t]["samples"] / 100
                cost_solved = d.get("cost")
            r["tok"].append(d["completion"] / d["calls"] if d.get("calls") else None)
            r["lat"].append(d.get("latency_median"))
            r["cost"].append(d.get("cost") if priced else None)
            r["per_solved"].append(cost_solved / solved if priced and solved else None)
        r["per_solved_na"] = t != "合计" and A["tiers"][t]["continuous"]
        cost.append(r)

    natural = lambda pid: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", pid)]  # noqa: E731
    diff = []
    for pid in common:
        pa, pb = A["per_problem"][pid], B["per_problem"][pid]
        d = pb["score"] - pa["score"]
        if (pa["continuous"] and abs(d) >= 20) or (not pa["continuous"] and (pa["solved"] > 0) != (pb["solved"] > 0)):
            diff.append({"pid": pid, "title": pa["title"], "tier": pa["tier"], "continuous": pa["continuous"],
                         "solved": [pa["solved"], pb["solved"]], "n": [pa["n"], pb["n"]], "score": [pa["score"], pb["score"]],
                         "d": d, "why": FAIL_NAME.get((pa if d > 0 else pb)["fail"], "")})
    diff.sort(key=lambda r: (L.TIERS.index(r["tier"]), -abs(r["d"]), natural(r["pid"])))

    usage = [{"cost": s["usage"]["cost"], "tok": s["usage"]["completion"] / max(s["usage"]["calls"], 1)} for s in stats]
    return {"names": [A["model"], B["model"]], "short": short, "tiers": tiers, "discrete": discrete, "pool": pool,
            "common": len(common), "scores": scores, "h2h": h2h, "cost": cost, "diff": diff, "usage": usage}


FIGS = set()  # figures drawn for this report (ladder_figures.py, needs matplotlib); a figure stands in for its table


def figure(stem, caption, fallback, width=1.0):
    """A bar chart in place of a table; width = share of the text width in the PDF (the figure's own size, unscaled)."""
    return ("fig", {"file": stem, "caption": caption, "table": fallback, "width": width})


def compare(stats):
    """Head-to-head section for two runs on the same problems: tables (or bar charts, when drawn) and a lead in words."""
    c = comparison(stats)
    a, b = c["short"]
    rows = []
    for r in c["scores"]:
        cells = [r["label"], str(r["problems"])]
        for k in ("pass1", "pass1_strict", "score"):
            x, y = r[k]
            cells += [NA, NA, NA] if x is None else [f1(x), f1(y), f_d(y - x)]
        rows.append(cells)
    t1 = table(["档位", "题数", a, b, "差", a, b, "差", a, b, "差"], rows, "l" + "r" * 10,
               [("", 2), ("pass@1（宽时限）↑", 3), ("pass@1（官方时限）↑", 3), ("平均得分（宽时限）↑", 3)])
    rows = [[r["label"], str(r["n"]), str(r["wins"][0]), str(r["tie"]), str(r["wins"][1]), f_p(r["p"])]
            + ([NA] * 4 if r["solve"] is None else [str(x) for x in r["solve"]]) for r in c["h2h"]]
    t2 = table(["档位", "题数", f"{a} 更好", "持平", f"{b} 更好", "符号检验 p", "都解出", f"只有 {a}", f"只有 {b}", "都没解出"], rows,
               "l" + "r" * 9, [("", 2), ("按每题平均得分", 4), ("按是否解出（至少一次）", 4)])
    rows = []
    for r in c["cost"]:
        cells = [r["label"]]
        fmt = {"tok": lambda v: U.fmt_tok(v), "lat": lambda v: f1(v, 0, " s"), "cost": lambda v: f"${v:.2f}",
               "per_solved": lambda v: f"${v:.3f}"}
        for k in ("tok", "lat", "cost", "per_solved"):
            cells += [NA if k == "per_solved" and r["per_solved_na"] else "–" if v is None else fmt[k](v) for v in r[k]]
        rows.append(cells)
    t3 = table(["档位", a, b, a, b, a, b, a, b], rows, "l" + "r" * 8,
               [("", 1), ("每次输出 token ↓", 2), ("延迟中位数 ↓", 2), ("费用 ↓", 2), ("每份解出答案的费用 ↓", 2)])
    t4 = table(["题目", "名称", "档位", a, b, a, b, "差", "落后一方的主要失败"],
               [[r["pid"], r["title"], r["tier"]] + ["–" if r["continuous"] else f"{s}/{n}" for s, n in zip(r["solved"], r["n"])]
                + [f"{x:.1f}" for x in r["score"]] + [f_d(r["d"]), r["why"]] for r in c["diff"]],
               "lllrrrrrl", [("", 3), ("解出 / 采样", 2), ("平均得分 ↑", 3), ("", 1)],
               tex_spec=r"@{}l>{\raggedright\arraybackslash}p{3.0cm}lrrrrr>{\raggedright\arraybackslash}p{2.2cm}@{}")

    # the lead in words: facts only, each with the number it rests on
    lead = [f"{a} = {c['names'][0]}，{b} = {c['names'][1]}；“差”一律为 {b} − {a}（百分点或分），正数表示 {b} 更高。"]
    pooled = next((r for r in c["scores"] if r["label"] == c["pool"]), None) or next((r for r in c["scores"] if not r["continuous"]), None)
    say = ""
    if pooled:
        x, y = pooled["pass1"]
        say = f"{pooled['label']} pass@1（宽时限）{a} {x:.1f}%、{b} {y:.1f}%（{f_d(y - x)}）"
    for r in c["scores"]:
        if r["continuous"]:
            say += f"；{r['label'].split()[0]} 平均得分 {a} {r['score'][0]:.1f}、{b} {r['score'][1]:.1f}（{f_d(r['score'][1] - r['score'][0])}）"
    tot = c["h2h"][-1]
    ptxt = "p < 0.001" if tot["p"] is not None and tot["p"] < 0.001 else f"p = {f_p(tot['p'])}"
    say += (f"。逐题按平均得分比较（{c['common']} 题）：{a} 更好 {tot['wins'][0]} 题，{b} 更好 {tot['wins'][1]} 题，持平 {tot['tie']} 题，"
            f"符号检验 {ptxt}（p < 0.05 才说明差距不太可能只是采样的随机波动）。")
    ua, ub = c["usage"]
    if ua["cost"] is not None and ub["cost"] is not None:
        say += (f"费用 {a} ${ua['cost']:.2f}、{b} ${ub['cost']:.2f}（{b} 是 {a} 的 {ub['cost'] / ua['cost']:.2f} 倍）；每次调用平均输出 token "
                f"{a} {U.fmt_tok(ua['tok'])}、{b} {U.fmt_tok(ub['tok'])}（{ub['tok'] / ua['tok']:.2f} 倍）。")
    lead.append(say)
    diff_text = "L1–L4 中一个模型至少解出一次、另一个一次都没解出的题，以及 L5 中平均得分相差 20 分以上的题；按差距从大到小。"
    return [("两个模型对比", lead + [
        ("h", "成绩"),
        figure("fig_scores", f"各档成绩。a–c 每档两根柱分别为 {a}、{b}，柱上为数值；d 为两者之差（{b} − {a}）。L5 为连续分，没有 pass@1。", t1),
        ("h", "逐题胜负"),
        "只比较两个模型都有结果的题。每题取所有采样的平均得分，相差不到 0.05 分记为持平；“解出”指至少一次采样解出（L5 为连续分，不适用）。"
        "符号检验只看胜负题数、不看差距大小。",
        figure("fig_h2h", "逐题胜负。a 按每题平均得分，柱右为符号检验 p 值；b 按是否解出（至少一次，L1–L4）。柱长为占该档题数的比例，柱内数字为题数，n 为题数。", t2),
        ("h", "成本与速度"),
        "每份解出答案的费用 = 该档费用 ÷ 宽时限下解出的采样数；合计只算 L1–L4（L5 没有“解出”）。费用按各自的标价计算，包括超时被切断的调用。",
        figure("fig_cost", "成本与速度。a 每次调用的平均输出 token（含思考）；b 每次调用的延迟中位数；c 各档费用；d 每份解出答案的费用。"
               "均为越低越好。", t3),
        ("h", "结果不同的题"), diff_text,
        figure("fig_diff", f"结果不同的题的平均得分之差（{b} − {a}），向左为 {a} 更好，向右为 {b} 更好。", None, 0.72), t4])]


def sections(stats):
    """The report body as data: [(title, [block, ...]), ...]; a block is a paragraph (str), a sub-heading
    ("h", text) or a table. Every table has the difficulty tiers as rows (one row per model and tier when several
    models are compared) and the metrics as columns."""
    multi = len(stats) > 1
    mh, ma = (["模型"], "l") if multi else ([], "")
    mc = lambda s: [s["model"]] if multi else []  # noqa: E731
    by_tier = lambda: [(t, s, s["tiers"][t]) for t in L.TIERS for s in stats if t in s["tiers"]]  # noqa: E731
    out = compare(stats) if len(stats) == 2 else []

    rows = []
    for t, s, st in by_tier():
        na = (lambda x: NA) if st["continuous"] else f1
        rows.append([TIER_NAME[t]] + mc(s) + [str(st["problems"]), str(st["samples"]), na(st["pass1"]), na(st["pass1_strict"]),
                     f1(st["score"]), f1(st["score_strict"]), na(st["passn"]) if st["n_per_problem"] > 1 else "–"])
    body = [table(["档位"] + mh + ["题数", "采样数", "宽时限", "官方时限", "宽时限", "官方时限", "pass@n ↑"], rows,
                  "l" + ma + "rrrrrrr", [("", 3 + len(mh)), ("pass@1 ↑", 2), ("平均得分 ↑", 2), ("", 1)])]
    many = sorted({(t, st["n_per_problem"]) for t, _, st in by_tier() if st["n_per_problem"] > 1})
    note = ["宽时限 = 官方时限的 5 倍，看算法对不对；官方时限看能否像人类选手一样在时限内通过。"]
    if many:
        note.append("pass@n = 每题多次采样中至少解出一次的题目比例（" + "、".join(f"{t} 每题 {n} 次" for t, n in many)
                    + "）；每题只采样 1 次的档记“–”。")
    if any(st["continuous"] for _, _, st in by_tier()):
        note.append("L5 按 0–100 连续计分（达到官方参考解约 60 分，超过越多分越高），没有“解出”一说，pass@1 记为“不适用”，只看平均得分。")
    out.append(("各档正确率", body + ["".join(note)]))

    keys = sorted({k for s in stats for k in s["subsets"]}, key=lambda k: (k.split("|")[0], k.split("|")[1] != "2026", k))
    if keys:
        rows = []
        for k in keys:
            for s in stats:
                st = s["subsets"].get(k)
                if st:
                    t, sub = k.split("|")
                    rows.append([TIER_NAME[t], SUBSET_NAME.get(sub, sub)] + mc(s) + [str(st["problems"]), str(st["samples"]),
                                                                                  f1(st["pass1"]), f1(st["score"])])
        text = ["同一档内 2026 年新题与 USACO 旧题分开统计（宽时限）。难度相当而新题明显更差时，旧题成绩可能受训练数据泄露抬高；只作提示，不作结论。"]
        if not any(k.endswith("|2026") for k in keys):
            text.append("本次评测还没有 2026 年的 EGOI/IOI 题，下表只是 USACO 两个赛季之间的对照（2025-26 赛季的题更新）。")
        out.append(("2026 新题与 USACO 旧题对照", text + [table(["档位", "子集"] + mh + ["题数", "采样数", "pass@1 ↑", "平均得分 ↑"],
                                                                rows, "ll" + ma + "rrrr")]))

    rows = [[TIER_NAME[t]] + mc(s) + [str(st["perf_n"]), f1(st["perf_geo"], 2, "×"), str(st["perf_faster"]), str(st["perf_2x"]),
                                      f1(st["mem_geo"], 2, "×")] for t, s, st in by_tier() if st["perf_n"]]
    if rows:
        out.append(("代码性能（相对官方解，同语言）", [
            "只比较解出的答案：在官方解最慢的 3 个测试点上与官方解交替各运行 3 次取中位数，倍数 = 答案 ÷ 官方解，各档取几何平均；"
            "小于 1 表示比官方解快。EGOI、FrontierCS 没有官方解，不参与。",
            table(["档位"] + mh + ["比较的答案数", "CPU 时间倍数 ↓", "快于官方解（份）", "慢 2 倍以上（份）", "峰值内存倍数 ↓"],
                  rows, "l" + ma + "rrrrr")]))

    if any(s["complexity"] for s in stats):
        body = ["k 为答案耗时（或峰值内存）相对官方解的增长幂次：k ≤ 0.75 且在官方解最重的测试点上至少快 2 倍为更优（可能是更好或更新颖的解法），"
                "0.75 < k < 1.33 为同阶，k ≥ 1.33 且至少慢 2 倍为更差，其余为不确定；方法见“评测维度与打分标准”。"]
        for kind, kname in (("time", "时间复杂度"), ("space", "空间复杂度")):
            rows = []
            for t in L.TIERS:
                for s in stats:
                    c = (s["complexity"].get(t) or {}).get(kind)
                    if c:
                        rows.append([TIER_NAME[t]] + mc(s) + [str(c["classes"].get(key, 0)) for key, _ in CPLX] + [f1(c["k_median"], 2)])
            body += [("h", kname), table(["档位"] + mh + [name for _, name in CPLX] + ["k 中位数"], rows, "l" + ma + "r" * (len(CPLX) + 1),
                                  [("", 1 + len(mh)), ("答案数", len(CPLX)), ("", 1)])]
        nov = [[TIER_NAME[t]] + mc(s) + [q, "时间" if k == "time" else "空间"] for s in stats for t, d in s["complexity"].items()
               for k in ("time", "space") for q in d[k]["better"]]
        body += ([("h", "增长慢于官方解、值得人工复核的答案"), table(["档位"] + mh + ["答案", "维度"], nov, "l" + ma + "ll")] if nov
                 else ["没有增长慢于官方解的答案。"])
        out.append(("时间与空间复杂度（相对官方解）", body))

    keys = [k for k in FAIL_ORDER if k != "slow" and any(st["fails"].get(k) for _, _, st in by_tier())]
    rows = [[TIER_NAME[t]] + mc(s) + [str(st["samples"]), str(sum(v for k, v in st["fails"].items() if k != "slow"))]
            + [str(st["fails"].get(k, 0)) for k in keys] + [str(st["fails"].get("slow", 0))] for t, s, st in by_tier()]
    text = "每份答案只记一个主要原因（判定顺序见“评测维度与打分标准”）。“只在官方时限下超时”的答案在宽时限下是解出的，单列。"
    if any(st["continuous"] for _, _, st in by_tier()):
        text += "L5 是连续分，拿到分的答案都记为“部分分”，这一档主要看得 0 分的原因。"
    out.append(("失败类型（答案数）", [text, table(
        ["档位"] + mh + ["答案数", "未解出"] + [FAIL_NAME[k] for k in keys] + ["只在官方时限下超时"], rows,
        "l" + ma + "r" * (len(keys) + 3), [("", 3 + len(mh)), ("未解出的主要原因", len(keys)), ("", 1)])]))

    if any((s["quality"] or {}).get("correct") for s in stats):
        rows = []
        for t in L.TIERS + ("合计",):
            for s in stats:
                q = s["quality"].get("correct" if t == "合计" else f"correct|{t}")
                if q:
                    rows.append([TIER_NAME.get(t, t)] + mc(s) + [str(q["n"]), f1(q["pylint_issues"], 2), f1(q["pylint_score"], 2),
                                 f1(q["issues_per_100sloc"], 2), f1(q["cc"], 2), f1(q["mi"], 1), f1(q["sloc"], 1)])
        body = ["只统计解出的 Python 答案（L1、L2），每份答案的平均值；工具与版本按 arXiv:2610.19167。",
                table(["档位"] + mh + ["答案数", "问题数 ↓", "得分 ↑", "每百行问题数 ↓", "圈复杂度 ↓", "可维护性 MI ↑", "SLOC"], rows,
                      "l" + ma + "rrrrrrr", [("", 2 + len(mh)), ("Pylint", 3), ("Radon", 3)])]
        if any((s["quality"]["correct"] or {}).get("sonar_maintainability") is not None for s in stats if s["quality"].get("correct")):
            rows = [[TIER_NAME.get(t, t)] + mc(s) + [f1(q[f"sonar_{k}"], 2) for k in ("maintainability", "reliability", "security")]
                    for t in L.TIERS + ("合计",) for s in stats
                    for q in [s["quality"].get("correct" if t == "合计" else f"correct|{t}")] if q]
            body += [table(["档位"] + mh + ["可维护性问题 ↓", "可靠性问题 ↓", "安全问题 ↓"], rows, "l" + ma + "rrr",
                           [("", 1 + len(mh)), ("SonarQube 10.4", 3)])]
        else:
            body.append("SonarQube 需要 Docker，这次评测的机器上没有，未测。")
        out.append(("静态质量（L1–L2，Python）", body))

    rows = []
    for t in L.TIERS + (None, "合计"):
        for s in stats:
            u = s["usage"]
            if t == "合计":
                d = {"calls": u["calls"], "completion": u["completion"], "latency_median": (u["latency"] or {}).get("median"),
                     "cost": u["cost"]}
            else:
                d = u["per_tier"].get(t) or u["per_tier"].get("null" if t is None else t)
                if not d:
                    continue
            cost = "–" if s["usage"]["cost"] is None else f"${d['cost']:.2f}"
            rows.append([TIER_NAME.get(t, t) if t else "已剔除的题"] + mc(s) + [str(d["calls"]), U.fmt_tok(d["completion"]),
                         U.fmt_tok(d["completion"] / d["calls"]) if d["calls"] else "–", f1(d.get("latency_median"), 0, " s"), cost])
    out.append(("用量与费用", [
        "调用数只计拿到回答或超时的调用；输出 token 含思考过程；延迟为一次调用从发出到收完的时间；费用按每次调用开始时的分时单价计算。超过时间上限被切断的请求，服务端不返回用量，其输出 token 按已输出的字数估算（每 token 约 3.57 字符）。",
        table(["档位"] + mh + ["调用数", "输出 token ↓", "每次输出 token ↓", "延迟中位数 ↓", "费用 ↓"], rows, "l" + ma + "rrrrr")]))

    body = []
    for s in stats:
        if multi:
            body.append(("h", s["model"]))
        natural = lambda pid: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", pid)]  # noqa: E731  fcs-6 before fcs-58
        order = sorted(s["per_problem"].items(), key=lambda kv: (L.TIERS.index(kv[1]["tier"]), natural(kv[0])))
        body.append(table(["题目", "名称", "档位", "子集", "解出 / 采样", "平均得分 ↑", "主要失败"],
                          [[pid, p["title"], p["tier"], p["subset"].replace("USACO ", "").replace("FrontierCS", "–"),
                            "–" if p["continuous"] else f"{p['solved']}/{p['n']}", f"{p['score']:.1f}",
                            FAIL_NAME.get(p["fail"], "") if not (p["continuous"] and p["fail"] == "partial") else ""]
                           for pid, p in order], "llllrrl", tex_spec=r"@{}l>{\raggedright\arraybackslash}p{3.4cm}llrr>{\raggedright\arraybackslash}p{3.1cm}@{}"))
    out.append(("逐题结果", body))
    return out


def _flat_head(t):
    """Markdown has no grouped headers: "pass@1 ↑" over "宽时限" becomes "pass@1 宽时限 ↑", "Pylint" over "得分 ↑"
    becomes "Pylint 得分 ↑"; descriptive groups ("答案数", "…原因") are dropped."""
    labels = []
    for label, span in t["groups"] or [("", len(t["head"]))]:
        labels += [label] * span
    out = []
    for g, h in zip(labels, t["head"]):
        if not g or g == "答案数" or g.endswith("原因"):
            out.append(h)
        else:
            arrow = g[-1] if g[-1] in "↑↓" else ""
            out.append(f"{g.rstrip(' ↑↓')} {h}" + (f" {arrow}" if arrow and arrow not in h else ""))
    return out


def md_table(t):
    head = _flat_head(t)
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join("---:" if a == "r" else "---" for a in t["align"]) + "|"]
                     + ["| " + " | ".join(r) + " |" for r in t["rows"]])


def tex_table(t, long=False):
    groups = ""
    if t["groups"]:
        cells, rules, col = [], [], 1
        for label, span in t["groups"]:
            if label:
                cells.append(rf"\multicolumn{{{span}}}{{c}}{{{tex(label)}}}")
                rules.append(rf"\cmidrule(lr){{{col}-{col + span - 1}}}")
            else:
                cells += [""] * span
            col += span
        groups = " & ".join(cells) + r" \\ " + " ".join(rules) + "\n"
    head = groups + " & ".join(tex(h) for h in t["head"]) + r" \\"
    rows = [" & ".join(tex(c) for c in r) + r" \\" for r in t["rows"]]
    if long:  # page-breaking (the per-problem list); a longtable cannot be scaled, so it gets p{} columns instead
        return "\n".join([r"{\footnotesize\setlength{\tabcolsep}{4pt}\begin{longtable}{" + (t["tex_spec"] or t["align"]) + "}", r"\toprule", head, r"\midrule\endhead"] + rows
                         + [r"\bottomrule", r"\end{longtable}}"])
    return "\n".join([r"\begin{center}\small", r"\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{%",
                      r"\begin{tabular}{" + (t["tex_spec"] or t["align"]) + "}", r"\toprule", head, r"\midrule"] + rows
                     + [r"\bottomrule", r"\end{tabular}}", r"\end{center}"])


def md_block(b):
    if isinstance(b, dict):
        return md_table(b)
    if isinstance(b, tuple):
        kind, x = b
        if kind == "fig":
            if x["file"] in FIGS:
                return f"![{x['caption']}]({x['file']}.png)\n\n{x['caption']}"
            return md_table(x["table"]) if x["table"] else ""
        if kind == "h":
            return f"### {x}"
        if kind == "ul":
            return "\n".join(f"- {i}" for i in x)
        if kind == "links":
            return "资料来源：" + "；".join(f"[{t}]({u})" for t, u in x)
    return b


def md_report(stats, date, author=None, db=None):
    names = " / ".join(s["model"] for s in stats)
    L_ = [f"# 阶梯代码评测报告：{names}", "", f"{date}　L1–L4：USACO 2024–26 与 EGOI/IOI 2026；L5：FrontierCS 算法赛道", ""]
    L_ += [f"- {n}" for n in notes(stats)] + ([""] if notes(stats) else [])
    for title, blocks in intro(stats, db or {}):
        L_ += [f"## {title}", ""] + [x for b in blocks for x in (md_block(b), "")]
    L_ += criteria_md()
    for title, blocks in sections(stats):
        L_ += [f"## {title}", ""] + [x for b in blocks for x in (md_block(b), "")]
    if author:
        L_ += ["---", "", f"由 {author} 创建于 {date}"]
    return "\n".join(L_) + "\n"


PREAMBLE = r"""\documentclass[11pt,a4paper,fontset=none]{ctexart}
\usepackage[margin=2.2cm]{geometry}
\usepackage{fontspec}
\newcommand{\WinFonts}{/mnt/c/Windows/Fonts/}
\IfFontExistsTF{Times New Roman}{\setmainfont{Times New Roman}\setsansfont{Times New Roman}}{%
  \IfFileExists{\WinFonts times.ttf}{\setmainfont{times.ttf}[Path=\WinFonts, BoldFont=timesbd.ttf, ItalicFont=timesi.ttf]%
    \setsansfont{times.ttf}[Path=\WinFonts, BoldFont=timesbd.ttf]}{\setmainfont{TeX Gyre Termes}\setsansfont{TeX Gyre Termes}}}
\newcommand{\KaiPath}{/System/Library/AssetsV2/com_apple_MobileAsset_Font8/88d6cc32a907955efa1d014207889413890573be.asset/AssetData/}
\IfFileExists{\KaiPath Kaiti.ttc}{%
  \setCJKmainfont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0, BoldFont=Kaiti.ttc, BoldFeatures={FontIndex=3}]
  \setCJKsansfont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0, BoldFont=Kaiti.ttc, BoldFeatures={FontIndex=3}]
  \setCJKmonofont{Kaiti.ttc}[Path=\KaiPath, FontIndex=0]}{%
  \IfFontExistsTF{Kaiti SC}{\setCJKmainfont{Kaiti SC}\setCJKsansfont{Kaiti SC}\setCJKmonofont{Kaiti SC}}{%
  \IfFileExists{\WinFonts simkai.ttf}{\setCJKmainfont{simkai.ttf}[Path=\WinFonts, AutoFakeBold=2.5]\setCJKsansfont{simkai.ttf}[Path=\WinFonts, AutoFakeBold=2.5]%
    \setCJKmonofont{simkai.ttf}[Path=\WinFonts]}{%
  \setCJKmainfont{FandolKai}\setCJKsansfont{FandolKai}\setCJKmonofont{FandolKai}}}}
\usepackage{amsmath}
\usepackage{booktabs,tabularx,longtable,array,graphicx,float}
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


def tex_url(u):
    return u.replace("%", r"\%").replace("#", r"\#")


def tex_block(b):
    if isinstance(b, dict):
        return tex_table(b, long=b["head"][0] == "题目")
    if isinstance(b, tuple):
        kind, x = b
        if kind == "fig":
            if x["file"] in FIGS:
                return "\n".join([r"\begin{figure}[H]\centering", rf"\includegraphics[width={x.get('width', 1.0):g}\linewidth]{{{x['file']}.pdf}}",
                                  rf"\caption{{{tex(x['caption'])}}}", r"\end{figure}"])
            return tex_table(x["table"]) if x["table"] else ""
        if kind == "h":
            return rf"\subsection*{{{tex(x)}}}"
        if kind == "ul":
            return "\n".join([r"\begin{itemize}"] + [rf"\item {tex(i)}" for i in x] + [r"\end{itemize}"])
        if kind == "links":
            return r"{\small 资料来源：" + "；".join(rf"\href{{{tex_url(u)}}}{{{tex(t)}}}" for t, u in x) + "}"
    return tex(b)


def tex_report(stats, date, author=None, db=None):
    names = " / ".join(tex(s["model"]) for s in stats)
    parts = [PREAMBLE.replace("__DATE__", date), r"\begin{document}", r"\begin{center}",
             r"{\LARGE\bfseries 阶梯代码评测报告}\\[0.5em]", rf"{{\Large {names}}}\\[0.4em]",
             rf"{{\small {date} \quad L1--L4：USACO 2024--26 与 EGOI/IOI 2026；L5：FrontierCS 算法赛道}}", r"\end{center}"]
    if notes(stats):
        parts += [r"\begin{itemize}"] + [rf"\item {tex(n)}" for n in notes(stats)] + [r"\end{itemize}"]
    for title, blocks in intro(stats, db or {}):
        parts.append(rf"\section{{{tex(title)}}}")
        parts += [tex_block(b) for b in blocks]
    parts.append(criteria_tex())
    for title, blocks in sections(stats):
        parts.append(rf"\section{{{tex(title)}}}")
        parts += [tex_block(b) for b in blocks]
    if author:
        parts.append(rf"\par\vspace{{2em}}\begin{{flushright}}由 {tex(author)} 创建于 {date}\end{{flushright}}")
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--from-json", help="re-render from a report.json written earlier (e.g. on a machine with matplotlib "
                                        "for the figures, without the run directories)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--prices", default="", help="model=in,hit,out;model2=... (per 1M tokens)")
    ap.add_argument("--names", default="", help="model=full name;model2=... (shown in the report instead of the API id)")
    ap.add_argument("--intro", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "models.json"),
                    help="model notes for the first section (keyed by API model id); '' for none")
    ap.add_argument("--author", default=os.environ.get("REPORT_AUTHOR", "Albert Huang"),
                    help="the last line reads: 由 <author> 创建于 <date>")
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
    if a.from_json:
        stats = json.load(open(a.from_json))
    elif a.runs:
        stats = []
        for d in a.runs:
            run = load(d, names=dict(x.split("=", 1) for x in filter(None, a.names.split(";"))))
            run["prices"] = per.get(run["model"], env)
            stats.append(analyze(run))
    else:
        ap.error("give run directories or --from-json")
    db = json.load(open(a.intro)) if a.intro and os.path.exists(a.intro) else {}
    os.makedirs(a.out, exist_ok=True)
    if len(stats) == 2:  # bar charts for the head-to-head section, where matplotlib is installed
        try:
            import ladder_figures
        except ImportError:
            print("no matplotlib: the head-to-head section keeps its tables")
        else:
            FIGS.update(ladder_figures.draw(comparison(stats), a.out))
    json.dump(stats, open(os.path.join(a.out, "report.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(a.out, "report.md"), "w").write(md_report(stats, a.date, a.author, db))
    open(os.path.join(a.out, "main.tex"), "w").write(tex_report(stats, a.date, a.author, db))
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
