"""Report of one or more multimodal ladder runs (cb mm): a capability profile and a ranking from the same items.

  python mm_report.py <run dir> [<run dir> ...] --out <report dir> [--date 2026-11-01] [--prices model=in,hit,out;...]
  python mm_report.py --from-json <report dir>/report.json --out <dir>     (re-render, e.g. with figures on the Mac)
  prices per 1M tokens: --prices, or PRICE_IN/PRICE_HIT/PRICE_OUT for every run not named there (as cb mm passes them)

Every run is scored here from its answers (mm_lib.score), so a change to answer extraction applies to old runs too.
Only items every run answered are compared. Per model: the score of each capability (mean over its items of the item's
mean over samples, 0-100) with a 95% bootstrap interval over items; the overall score is the equal-weight mean of the
capabilities, so a capability with more items does not count more. Ranking: for every pair, the overall difference
with a 95% interval from a paired bootstrap that resamples items within each capability; a model's rank is 1 + the
number of models whose interval against it lies wholly above zero (models no one is clearly better than share rank 1).
Per-item wins and losses get the exact sign test of ladder_report.py.
"""
import argparse
import collections
import datetime
import json
import os
import random
import shutil
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_report as LR  # noqa: E402  (tables, Markdown/LaTeX rendering, sign test, model notes)
import lcb_usage as U  # noqa: E402
import mm_lib as M  # noqa: E402

B = 2000  # bootstrap resamples
TIE = 1e-9


def jl(path):
    return [json.loads(x) for x in open(path)] if os.path.exists(path) else []


def load(run_dir, prices=None, names=None):
    """One run, scored: {model, name, info, items: {id: {cap, tier, source, scores, unread}}, usage, failures}."""
    info = json.load(open(os.path.join(run_dir, "run.json")))
    last = {}
    for r in jl(os.path.join(run_dir, "answers.jsonl")):
        last[r["q"]] = r
    calls = jl(os.path.join(run_dir, "usage.jsonl"))
    items, fails = {}, collections.Counter()
    for q, r in sorted(last.items()):
        if r.get("finish") == "error":  # the API never answered (retries used up): not the model's failure, left out
            fails["error"] += 1
            continue
        it = M.load_item(r["id"])
        d = items.setdefault(r["id"], {"cap": it["capability"], "tier": it["tier"], "source": it["source"],
                                       "scores": [], "unread": 0})
        if r.get("finish") == "timeout":
            fails["timeout"] += 1
            d["scores"].append(0.0)
            continue
        if r.get("finish") == "length":
            fails["length"] += 1
        s, got = M.score(it, r.get("text", ""))
        if got is None:
            d["unread"] += 1
            fails["unread"] += 1
        d["scores"].append(s)
    ok = [c for c in calls if "error" not in c]
    tok = [U.tokens(c.get("usage")) for c in ok]
    usage = {"calls": len(ok), "prompt": sum(t[0] for t in tok), "completion": sum(t[2] for t in tok),
             "reasoning": sum(t[3] for t in tok), "latency": U.stats([c["end"] - c["start"] for c in ok]),
             "cost": sum(U.call_cost(c, prices) for c in ok) if prices else None}
    name = (names or {}).get(info["model"]) or info.get("name") or info["model"]
    return {"model": name, "model_id": info["model"], "info": {k: info.get(k) for k in (
        "k", "smoke", "version", "temperature", "max_tokens", "reasoning_effort", "detail", "started")},
        "items": items, "usage": usage, "failures": dict(fails), "samples": sum(len(d["scores"]) for d in items.values())}


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def common_items(stats):
    ids = set.intersection(*(set(s["items"]) for s in stats)) if stats else set()
    return sorted(i for i in ids if all(s["items"][i]["scores"] for s in stats))


def profile(stats):
    """Scores on the items every run answered: per capability, tier and source, the overall score, intervals, ranks."""
    ids = common_items(stats)
    cap_of = {i: stats[0]["items"][i]["cap"] for i in ids}
    caps = [c for c in M.CAPS if any(cap_of[i] == c for i in ids)]
    by_cap = {c: [i for i in ids if cap_of[i] == c] for c in caps}
    item_mean = [{i: mean(s["items"][i]["scores"]) for i in ids} for s in stats]

    def cap_scores(r, pick):
        return {c: 100 * mean([item_mean[r][i] for i in pick[c]]) for c in caps}

    point = [cap_scores(r, by_cap) for r in range(len(stats))]
    overall = [mean(list(p.values())) for p in point]
    rng = random.Random(0)
    boot_cap = [[] for _ in stats]
    boot_all = [[] for _ in stats]
    for _ in range(B):
        pick = {c: [rng.choice(v) for _ in v] for c, v in by_cap.items()}
        for r in range(len(stats)):
            cs = cap_scores(r, pick)
            boot_cap[r].append(cs)
            boot_all[r].append(mean(list(cs.values())))

    def ci(xs):
        xs = sorted(xs)
        return [xs[int(0.025 * (len(xs) - 1))], xs[int(0.975 * (len(xs) - 1))]]

    cap_ci = [{c: ci([b[c] for b in boot_cap[r]]) for c in caps} for r in range(len(stats))]
    all_ci = [ci(boot_all[r]) for r in range(len(stats))]
    pairs = {}
    for a in range(len(stats)):
        for b in range(len(stats)):
            if a == b:
                continue
            d = [x - y for x, y in zip(boot_all[a], boot_all[b])]
            wins = sum(item_mean[a][i] > item_mean[b][i] + TIE for i in ids)
            losses = sum(item_mean[b][i] > item_mean[a][i] + TIE for i in ids)
            pairs[f"{a},{b}"] = {"diff": overall[a] - overall[b], "ci": ci(d), "wins": wins, "losses": losses,
                                 "ties": len(ids) - wins - losses, "p": LR.sign_test(wins, losses)}
    rank = [1 + sum(pairs[f"{b},{a}"]["ci"][0] > 0 for b in range(len(stats)) if b != a) for a in range(len(stats))]
    tiers = [t for t in M.TIERS if any(stats[0]["items"][i]["tier"] == t for i in ids)]
    tier = {t: {"n": sum(stats[0]["items"][i]["tier"] == t for i in ids),
                "scores": [100 * mean([item_mean[r][i] for i in ids if stats[0]["items"][i]["tier"] == t])
                           for r in range(len(stats))]} for t in tiers}
    src = collections.defaultdict(list)
    for i in ids:
        src[(cap_of[i], stats[0]["items"][i]["source"])].append(i)
    sources = [{"cap": c, "source": s, "n": len(v), "tiers": sorted({stats[0]["items"][i]["tier"] for i in v}),
                "scores": [100 * mean([item_mean[r][i] for i in v]) for r in range(len(stats))]}
               for (c, s), v in sorted(src.items(), key=lambda kv: (M.CAPS.index(kv[0][0]), kv[0][1]))]
    return {"n": len(ids), "caps": caps, "n_cap": {c: len(v) for c, v in by_cap.items()}, "cap": point, "cap_ci": cap_ci,
            "overall": overall, "overall_ci": all_ci, "pairs": pairs, "rank": rank, "tier": tier, "sources": sources,
            "names": [s["model"] for s in stats]}


# ---------------------------------------------------------------- text

def f_ci(x, c):
    return f"{x:.1f}（{c[0]:.1f}–{c[1]:.1f}）"


def order(p):
    return sorted(range(len(p["names"])), key=lambda r: (p["rank"][r], -p["overall"][r]))


def summary(stats, p):
    names, o = p["names"], order(p)
    caps = "、".join(M.CAP_NAME[c] for c in p["caps"])
    s = (f"在 {p['n']} 道题（{len(p['caps'])} 项能力：{caps}）上，按各项等权的总分："
         + "；".join(f"第 {p['rank'][r]} 名 {names[r]} {f_ci(p['overall'][r], p['overall_ci'][r])}" for r in o) + "（括号内为 95% 区间）。")
    for a, b in zip(o, o[1:]):
        d = p["pairs"][f"{a},{b}"]
        sig = d["ci"][0] > 0
        s += (f"{names[a]} 比 {names[b]} 高 {d['diff']:.1f} 分（区间 {d['ci'][0]:+.1f} 至 {d['ci'][1]:+.1f}），"
              + ("差距显著" if sig else "区间包含 0，判为平手") + f"；逐题比较 {d['wins']} 题更好、{d['losses']} 题更差、"
              f"{d['ties']} 题相同（符号检验 p {('< 0.001' if (d['p'] or 1) < 0.001 else '= ' + LR.f_p(d['p']))}）。")
    for r in o:
        cs = p["cap"][r]
        hi, lo = max(cs, key=cs.get), min(cs, key=cs.get)
        s += (f"{names[r]} 各项得分相同（{cs[hi]:.1f}）。" if cs[hi] - cs[lo] < 0.05 else
              f"{names[r]} 最强的是{M.CAP_NAME[hi]}（{cs[hi]:.1f}），最弱的是{M.CAP_NAME[lo]}（{cs[lo]:.1f}）。")
    costs = [st["usage"]["cost"] for st in stats]
    if all(c is not None for c in costs):
        s += "总费用 " + " / ".join(f"${c:.2f}" for c in costs) + f"（依次为 {' / '.join(s_['model'] for s_ in stats)}）。"
    return s


def notes(stats, p):
    k = sorted({s["info"].get("k") for s in stats})
    out = [f"每道题每个模型答 {'/'.join(map(str, k))} 次，题目得分取各次的平均；只比较所有模型都答过的 {p['n']} 道题。"
           "题目抽自公开评测集，按来源的难度分为 L1–L4，分数不能和这些评测集的官方榜单直接比较。",
           "总分是各项能力的等权平均，不按题数加权。95% 区间来自 2000 次按题重抽样（bootstrap）；两两差值的区间在每项能力内"
           "成对重抽样。区间包含 0 的两个模型判为平手，名次相同。"]
    widths = [(d["ci"][1] - d["ci"][0]) / 2 for d in p["pairs"].values()]
    if widths:
        out.append(f"按这套题的题量，两两总分差的 95% 区间半宽约 ±{statistics.median(widths):.1f} 分：比这小的差距分不出来。")
    for s in stats:
        f, i = s["failures"], s["info"]
        set_ = "，".join(x for x in (
            f"reasoning_effort = {i['reasoning_effort']}" if i.get("reasoning_effort") else "",
            f"max_tokens = {i['max_tokens']}" if i.get("max_tokens") else "max_tokens 不设上限",
            f"temperature = {i['temperature']}" if i.get("temperature") is not None else "temperature 用厂商默认值",
            f"图片 detail = {i['detail']}" if i.get("detail") else "") if x)
        bad = "，".join(x for x in (f"{f['unread']} 次读不出答案" if f.get("unread") else "",
                                     f"{f['timeout']} 次生成超时" if f.get("timeout") else "",
                                     f"{f['length']} 次输出被截断" if f.get("length") else "",
                                     f"{f['error']} 次接口始终没有回答（不计入）" if f.get("error") else "") if x)
        out.append(f"{s['model']}：{set_}。" + (f"{bad}；读不出答案、超时和截断都计 0 分。" if bad else ""))
    return out


CRITERIA = [("选择题", "取回答最后一行 “Answer: X” 中的选项字母，与标准答案相同得 1 分"),
            ("是 / 否", "取最后的 yes 或 no，与标准答案相同得 1 分"),
            ("短答案", "数字在相对误差 1% 内（ChartQA 按其规则放宽到 5%）得 1 分；文字答案规范化（小写、去冠词和标点）后完全相同得 1 分"),
            ("文档问答", "ANLS：与最接近的标准答案的归一化编辑距离相似度，低于 0.5 记 0（DocVQA 的规则）"),
            ("界面定位", "模型给出 0–1000 的相对坐标，换算到原图后落在目标框内得 1 分"),
            ("空间指点", "同样给出 0–1000 的相对坐标，落在目标物体的掩膜内得 1 分（RefSpatial-Bench）"),
            ("视频", "所有模型都拿到同样的若干帧（按时间均匀抽取的图片），按上面的题型判分")]


def sections(stats, p):
    names, n = p["names"], len(stats)
    out = []
    head = ["能力", "题数"] + names
    rows = [[M.CAP_NAME[c], str(p["n_cap"][c])] + [f_ci(p["cap"][r][c], p["cap_ci"][r][c]) for r in range(n)] for c in p["caps"]]
    rows.append(["总分（等权）", str(p["n"])] + [f_ci(p["overall"][r], p["overall_ci"][r]) for r in range(n)])
    t1 = LR.table(head, rows, "lr" + "r" * n, groups=[("", 2), ("得分（0–100，括号内 95% 区间）↑", n)])
    out.append(("能力画像", ["每项能力的得分是该项各题得分的平均（0–100）。", LR.figure("fig_profile", "各项能力得分（误差线为 95% 区间）", t1)]
                + ([t1] if "fig_profile" in LR.FIGS else [])))
    o = order(p)
    rows = [[str(p["rank"][r]), names[r], f_ci(p["overall"][r], p["overall_ci"][r])] for r in o]
    t2 = LR.table(["名次", "模型", "总分 ↑"], rows, "llr")
    blocks = ["名次 = 1 + 明显强于它的模型数；区间包含 0 的模型名次相同。", t2]
    if n > 1:
        rows = []
        for j, a in enumerate(o):  # every pair once, the higher-placed model first
            for b in o[j + 1:]:
                d = p["pairs"][f"{a},{b}"]
                rows.append([f"{names[a]} − {names[b]}", LR.f_d(d["diff"]), f"{d['ci'][0]:+.1f} 至 {d['ci'][1]:+.1f}",
                             str(d["wins"]), str(d["losses"]), str(d["ties"]), LR.f_p(d["p"])])
        blocks += ["两两比较：总分差与 95% 区间；逐题比较的胜、负、平题数与符号检验。",
                   LR.table(["比较", "总分差", "95% 区间", "胜", "负", "平", "p"], rows, "lrrrrrr")]
    out.append(("排名", blocks))
    rows = [[M.TIER_NAME[t], str(v["n"])] + [f"{x:.1f}" for x in v["scores"]] for t, v in p["tier"].items()]
    out.append(("按难度", ["各档的题来自不同评测集（见下表），这里把所有能力合在一起按题平均。",
                         LR.table(["难度", "题数"] + names, rows, "lr" + "r" * n, groups=[("", 2), ("得分 ↑", n)])]))
    rows = [[M.CAP_NAME[s["cap"]], s["source"], "/".join(s["tiers"]), str(s["n"])] + [f"{x:.1f}" for x in s["scores"]]
            for s in p["sources"]]
    out.append(("按来源", ["每个来源评测集上的得分，只是抽样的子集，不等于该评测集的完整成绩。",
                         LR.table(["能力", "来源", "难度", "题数"] + names, rows, "lllr" + "r" * n, groups=[("", 4), ("得分 ↑", n)])]))
    rows = []
    for s in stats:
        u = s["usage"]
        lat = u["latency"]
        rows.append([s["model"], str(u["calls"]), U.fmt_tok(u["prompt"] / max(u["calls"], 1)),
                     U.fmt_tok(u["completion"] / max(u["calls"], 1)), f"{lat['median']:.0f}" if lat else "–",
                     f"${u['cost']:.2f}" if u["cost"] is not None else "–",
                     f"${u['cost'] / max(len(s['items']), 1):.3f}" if u["cost"] is not None else "–"])
    out.append(("成本与速度", [LR.table(["模型", "调用次数", "平均输入 token ↓", "平均输出 token ↓", "延迟中位数 s ↓", "总费用 ↓", "每题费用 ↓"],
                                      rows, "lrrrrrr")]))
    out.append(("评分规则", [LR.table(["题型", "怎么判"], [list(r) for r in CRITERIA], "ll",
                                    tex_spec=r"@{}p{2.2cm}>{\raggedright\arraybackslash}p{13.6cm}@{}")]))
    return out


def md_report(stats, p, date, author=None, db=None):
    L_ = [f"# 多模态阶梯评测报告：{' / '.join(p['names'])}", "", f"{date}", "", "## 总结", "", summary(stats, p), "", "说明：", ""]
    L_ += [f"- {x}" for x in notes(stats, p)] + [""]
    for title, blocks in LR.intro(stats, db or {}) + sections(stats, p):
        L_ += [f"## {title}", ""] + [x for b in blocks for x in (LR.md_block(b), "")]
    if author:
        L_ += ["---", "", f"由 {author} 创建于 {date}"]
    return "\n".join(L_) + "\n"


def tex_report(stats, p, date, author=None, db=None):
    names = " / ".join(LR.tex(n) for n in p["names"])
    parts = [LR.PREAMBLE.replace("__DATE__", date).replace("阶梯代码评测", "多模态阶梯评测"), r"\begin{document}",
             r"\begin{center}", r"{\LARGE\bfseries 多模态阶梯评测报告}\\[0.5em]", rf"{{\Large {names}}}\\[0.4em]",
             rf"{{\small {date}}}", r"\end{center}", r"\section{总结}", LR.tex(summary(stats, p)), r"\par 说明：",
             r"\begin{itemize}"] + [rf"\item {LR.tex(x)}" for x in notes(stats, p)] + [r"\end{itemize}"]
    for title, blocks in LR.intro(stats, db or {}) + sections(stats, p):
        parts.append(rf"\section{{{LR.tex(title)}}}")
        parts += [LR.tex_block(b) for b in blocks]
    if author:
        parts.append(rf"\par\vspace{{2em}}\begin{{flushright}}由 {LR.tex(author)} 创建于 {date}\end{{flushright}}")
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--from-json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--prices", default="", help="model=in,hit,out;model2=... (per 1M tokens)")
    ap.add_argument("--names", default="", help="model=full name;model2=...")
    ap.add_argument("--intro", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "models.json"))
    ap.add_argument("--author", default=os.environ.get("REPORT_AUTHOR", "Albert Huang"))
    a = ap.parse_args()
    per = {}
    for x in filter(None, a.prices.split(";")):
        m, v = x.split("=")
        i, h, o = map(float, v.split(","))
        per[m] = {"in": i, "hit": h, "out": o}
    env = None  # one model's prices from PRICE_IN/PRICE_HIT/PRICE_OUT, as the ladder report
    if os.environ.get("PRICE_IN") and os.environ.get("PRICE_OUT"):
        env = {"in": float(os.environ["PRICE_IN"]), "hit": float(os.environ.get("PRICE_HIT") or os.environ["PRICE_IN"]),
               "out": float(os.environ["PRICE_OUT"])}
    if a.from_json:
        data = json.load(open(a.from_json))
        stats, p = data["stats"], data["profile"]
    elif a.runs:
        names = dict(x.split("=", 1) for x in filter(None, a.names.split(";")))
        stats = []
        for d in a.runs:
            info = json.load(open(os.path.join(d, "run.json")))
            stats.append(load(d, per.get(info["model"], env), names))
        p = profile(stats)
    else:
        ap.error("give run directories or --from-json")
    if not p["n"]:
        sys.exit("no item was answered by every run")
    db = json.load(open(a.intro)) if a.intro and os.path.exists(a.intro) else {}
    os.makedirs(a.out, exist_ok=True)
    try:
        import mm_figures
    except ImportError:
        print("no matplotlib: the report keeps its tables")
    else:
        LR.FIGS.update(mm_figures.draw(p, a.out))
    # item ids and scores only (no question text or images), so a report directory can be committed
    json.dump({"stats": stats, "profile": p}, open(os.path.join(a.out, "report.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(a.out, "report.md"), "w").write(md_report(stats, p, a.date, a.author, db))
    open(os.path.join(a.out, "main.tex"), "w").write(tex_report(stats, p, a.date, a.author, db))
    open(os.path.join(a.out, "build.sh"), "w").write("#!/bin/bash\n# PDF of this report (xelatex with ctex)\n"
                                                    "cd \"$(dirname \"$0\")\" && xelatex -interaction=nonstopmode main.tex >/dev/null && "
                                                    "xelatex -interaction=nonstopmode main.tex >/dev/null && echo \"$(pwd)/main.pdf\"\n")
    print(f"report: {a.out}/report.md")
    if shutil.which("xelatex"):
        r = subprocess.run(["bash", os.path.join(a.out, "build.sh")], capture_output=True, text=True)
        print(r.stdout.strip() or "xelatex failed: see main.log")


if __name__ == "__main__":
    main()
