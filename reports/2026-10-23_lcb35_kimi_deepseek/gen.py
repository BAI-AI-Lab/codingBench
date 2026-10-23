"""Build data.tex (LaTeX tables and macros) from the three LiveCodeBench runs copied under runs/<model>/.

Each runs/<model>/ holds eval_all.json (LCB's *_eval_all.json) and usage.jsonl (cb's per-call log).
"""
import collections
import datetime
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = [  # key, display name, short name, price per 1M tokens (USD): (miss, hit, out) peak, off-peak or flat
    ("kimi-k3.1-pro", "Kimi K3.1 Pro", "Kimi", {"flat": (2.0, 0.2, 10.0)}),
    ("deepseek-flash", "DeepSeek-V4.1-Flash", "DS-Flash", {"peak": (0.3, 0.006, 1.2), "off": (0.15, 0.003, 0.6)}),
    ("deepseek-v4-pro", "DeepSeek-V4-Pro", "DS-Pro", {"peak": (1.32, 0.044, 3.96), "off": (0.66, 0.022, 1.98)}),
]
ERR = {-2: "答案错误", -3: "超时", -4: "运行/编译错误", -1: "其他错误"}
# Re-judge of every AtCoder answer with real stdin/stdout and checkers (rejudge.py on the server); LeetCode
# answers keep LCB's verdict (function calls, untouched by the stdin/stdout problems).
REJUDGE, KIND = {}, {}  # verdict, and the re-judged failure kind
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rejudge_atcoder.jsonl")):
    r = json.loads(line)
    if "model" in r:
        n, t = map(int, (r.get("checker") or r.get("exact")).split("/"))
        REJUDGE[(r["model"], r["q"])] = n == t
        if n != t:
            KIND[(r["model"], r["q"])] = {"WA": "答案错误", "RE": "运行错误", "TLE": "超时"}[r["failed_tests"][0][1]]
USER_VERIFIED = {("kimi-k3.1-pro", "abc399_e")}  # the user re-ran it and it was correct
problems = {p["question_id"]: p for p in json.load(open(os.path.join(HERE, "problems35.json")))}
ORDER = sorted(problems, key=lambda q: ({"medium": 0, "hard": 1}[problems[q]["difficulty"]],
                                       problems[q]["platform"], problems[q]["contest_date"], q))


def peak(t):  # DeepSeek peak hours: 01:00-04:00 and 06:00-10:00 UTC, Mon-Fri
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return d.weekday() < 5 and (1 <= d.hour < 4 or 6 <= d.hour < 10)


def tokens(u):
    u = u or {}
    hit = u.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("cached_tokens") or 0
    reason = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return u.get("prompt_tokens") or 0, hit, u.get("completion_tokens") or 0, reason


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def load(key, prices):
    d = os.path.join(HERE, "runs", key)
    rows = {r["question_id"]: r for r in json.load(open(os.path.join(d, "eval_all.json")))}
    calls = [json.loads(l) for l in open(os.path.join(d, "usage.jsonl")) if l.strip()]
    by_q, errors, cost, served = {}, [], 0.0, collections.Counter()
    tot = [0, 0, 0, 0]
    for c in calls:
        if "error" in c:
            errors.append(c)
            continue
        text = "\n".join(m.get("content") or "" for m in c["messages"])
        hit = [q for q, p in problems.items() if p["question_content"].strip() in text]
        assert len(hit) == 1, hit
        by_q.setdefault(hit[0], []).append(c)
        t = tokens(c.get("usage"))
        tot = [a + b for a, b in zip(tot, t)]
        miss_p, hit_p, out_p = prices["flat"] if "flat" in prices else prices["peak" if peak(c["start"]) else "off"]
        cost += ((t[0] - t[1]) * miss_p + t[1] * hit_p + t[2] * out_p) / 1e6
        served[c.get("model") or "?"] += 1
    busy, cur = 0.0, None  # minutes during which at least one successful request was running
    for a, b in sorted((c["start"], c["end"]) for cs in by_q.values() for c in cs):
        if cur and a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            busy += (cur[1] - cur[0]) if cur else 0
            cur = [a, b]
    busy += (cur[1] - cur[0]) if cur else 0
    finish = collections.Counter(f for cs in by_q.values() for f in (cs[-1].get("finish") or []))
    m = {"rows": rows, "by_q": by_q, "errors": errors, "cost": cost, "tot": tot, "served": served,
         "wall": busy / 60, "finish": finish}
    m["lat"] = {q: cs[-1]["end"] - cs[-1]["start"] for q, cs in by_q.items()}
    m["out"] = {q: tokens(cs[-1].get("usage"))[2] for q, cs in by_q.items()}
    m["lcb"] = {q: bool(r["graded_list"][0]) for q, r in rows.items()}
    m["passed"], m["mark"] = {}, {}
    for q in rows:
        ok = REJUDGE.get((key, q), m["lcb"][q])
        if (key, q) in USER_VERIFIED:
            ok, m["mark"][q] = True, "$^{\\dagger}$"
        elif ok and not m["lcb"][q]:
            m["mark"][q] = "$^{*}$"
        m["passed"][q] = ok
    m["why"] = {}
    for q, r in rows.items():
        if m["passed"][q]:
            continue
        if (key, q) in KIND:
            m["why"][q] = KIND[(key, q)]
            continue
        if q not in by_q:
            m["why"][q] = "未作答"
        elif not r["code_list"][0].strip():
            m["why"][q] = "无代码"
        else:
            try:
                m["why"][q] = ERR.get(json.loads(r["metadata"][0]).get("error_code"), "其他错误")
            except (ValueError, IndexError, TypeError):
                m["why"][q] = "其他错误"
    return m


R = {k: load(k, p) for k, _, _, p in MODELS}
for k, m in R.items():
    assert set(m["rows"]) == set(problems), k

L = []


def mac(name, val):
    L.append(f"\\newcommand{{\\{name}}}{{{val}}}")


def ktok(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


# headline macros, e.g. \KimiPass, \DSFlashPass
for k, name, short, _ in MODELS:
    m, tag = R[k], short.replace("-", "")
    mac(f"{tag}Pass", sum(m["passed"].values()))
    mac(f"{tag}Rate", f"{100 * sum(m['passed'].values()) / len(problems):.1f}")
    mac(f"{tag}Answered", len(m["by_q"]))
    mac(f"{tag}Cost", f"{m['cost']:.2f}")
    mac(f"{tag}Wall", f"{m['wall']:.0f}")
    mac(f"{tag}Served", ", ".join(f"\\texttt{{{s}}}" for s in m["served"]))

# overall table
diff_n = collections.Counter(p["difficulty"] for p in problems.values())
plat_n = collections.Counter(p["platform"] for p in problems.values())
rows = []


def cell(vals, fmt, best=max):
    b = best(vals)
    return [("\\textbf{" + fmt(v) + "}") if v == b else fmt(v) for v in vals]


def by(m, f):
    return sum(m["passed"][q] for q in problems if f(problems[q]))


ms = [R[k] for k, *_ in MODELS]
rows.append(["通过：LCB 原始判分"] + cell([sum(m["lcb"].values()) for m in ms], lambda v: f"{v}（{100 * v / 35:.1f}\\%）"))
rows.append(["通过：复核后（总计 35）"] + cell([sum(m["passed"].values()) for m in ms], lambda v: f"{v}（{100 * v / 35:.1f}\\%）"))
rows.append([f"中等（{diff_n['medium']}）"] + cell([by(m, lambda p: p["difficulty"] == "medium") for m in ms], str))
rows.append([f"困难（{diff_n['hard']}）"] + cell([by(m, lambda p: p["difficulty"] == "hard") for m in ms], str))
rows.append([f"AtCoder（{plat_n['atcoder']}）"] + cell([by(m, lambda p: p["platform"] == "atcoder") for m in ms], str))
rows.append([f"LeetCode（{plat_n['leetcode']}）"] + cell([by(m, lambda p: p["platform"] == "leetcode") for m in ms], str))
rows.append(["实际作答题数"] + [str(len(m["by_q"])) for m in ms])
rows.append(["有效运行时间（分钟）"] + cell([m["wall"] for m in ms], lambda v: f"{v:.0f}", min))
rows.append(["每题延迟中位数（秒）"] + cell([statistics.median(m["lat"].values()) for m in ms], lambda v: f"{v:.0f}", min))
rows.append(["每题延迟 P90（秒）"] + cell([pct(list(m["lat"].values()), 90) for m in ms], lambda v: f"{v:.0f}", min))
rows.append(["每题延迟最长（秒）"] + cell([max(m["lat"].values()) for m in ms], lambda v: f"{v:.0f}", min))
rows.append(["输出速度中位数（token/秒）"] + cell(
    [statistics.median(m["out"][q] / m["lat"][q] for q in m["lat"] if m["lat"][q] > 0) for m in ms], lambda v: f"{v:.0f}"))
rows.append(["输出 token 合计"] + [ktok(m["tot"][2]) for m in ms])
rows.append(["其中思考 token 占比"] + [f"{100 * m['tot'][3] / m['tot'][2]:.0f}\\%" if m["tot"][2] else "—" for m in ms])
rows.append(["每题输出 token 中位数"] + cell([statistics.median(m["out"].values()) for m in ms], ktok, min))
rows.append(["输入 token 合计（缓存命中）"] + [f"{ktok(m['tot'][0])}（{ktok(m['tot'][1])}）" for m in ms])
rows.append(["费用（美元，按 token 计）"] + cell([m["cost"] for m in ms], lambda v: f"\\${v:.2f}", min))
rows.append(["每道通过题的费用（美元）"] + cell([m["cost"] / max(1, sum(m["passed"].values())) for m in ms],
                                       lambda v: f"\\${v:.3f}", min))
rows.append(["API 出错次数"] + [str(len(m["errors"])) for m in ms])
L.append("\\newcommand{\\OverallRows}{%")
L += [" & ".join(r) + " \\\\" for r in rows]
L.append("}")

# per difficulty: tokens & latency
L.append("\\newcommand{\\DiffRows}{%")
for d, dn in [("medium", "中等"), ("hard", "困难")]:
    qs = [q for q in problems if problems[q]["difficulty"] == d]
    for (k, name, short, _), m in zip(MODELS, ms):
        have = [q for q in qs if q in m["out"]]
        L.append(f"{dn} & {name} & {sum(m['passed'][q] for q in qs)}/{len(qs)} & "
                 f"{statistics.median(m['lat'][q] for q in have):.0f} & {ktok(statistics.mean(m['out'][q] for q in have))} & "
                 f"{ktok(max(m['out'][q] for q in have))} \\\\")
L.append("}")

# per-problem matrix
L.append("\\newcommand{\\ProblemRows}{%")
prev = None
for q in ORDER:
    p = problems[q]
    prev = p["difficulty"]
    cells = []
    for m in ms:
        if m["passed"][q]:
            s = "\\ok" + m["mark"].get(q, "")
        else:
            s = "\\no{" + m["why"][q] + "}"
        if q in m["out"]:
            s += f" & {m['out'][q] / 1e3:.1f}k & {m['lat'][q]:.0f}"
        else:
            s += " & — & —"
        cells.append(s)
    title = p["question_title"].replace("^", "\\^{}").replace("_", "\\_").replace("&", "\\&")
    if len(title) > 26:
        title = title[:25] + "…"
    L.append(f"\\texttt{{{q.replace('_', chr(92) + '_')}}} & {title} & {'中' if p['difficulty'] == 'medium' else '难'} & "
             + " & ".join(cells) + " \\\\")
L.append("}")

# agreement
solved = {k: {q for q in problems if R[k]["passed"][q]} for k, *_ in MODELS}
allk = [k for k, *_ in MODELS]
mac("AllSolved", len(set.intersection(*solved.values())))
mac("NoneSolved", len([q for q in problems if not any(q in solved[k] for k in allk)]))
uniq = []
for k, name, short, _ in MODELS:
    only = sorted(solved[k] - set.union(*(solved[j] for j in allk if j != k)))
    uniq.append(f"{name}：" + ("、".join(f"\\texttt{{{q.replace('_', chr(92) + '_')}}}" for q in only) if only else "无"))
mac("OnlySolved", "；".join(uniq))
none = [q for q in problems if not any(q in solved[k] for k in allk)]
mac("NoneSolvedList", "、".join(f"\\texttt{{{q.replace('_', chr(92) + '_')}}}" for q in none) or "无")

# chart coordinates: pass by difficulty, output tokens per difficulty
for (k, name, short, _), m in zip(MODELS, ms):
    tag = short.replace("-", "")
    med = by(m, lambda p: p["difficulty"] == "medium")
    hard = by(m, lambda p: p["difficulty"] == "hard")
    mac(f"{tag}Coords", f"(中等,{100 * med / diff_n['medium']:.1f}) (困难,{100 * hard / diff_n['hard']:.1f}) "
                        f"(总计,{100 * (med + hard) / 35:.1f})")

def example(q):
    parts = []
    for (k, name, short, _), m in zip(MODELS, ms):
        res = "\\ok" if m["passed"][q] else "\\no{" + m["why"][q] + "}"
        extra = f"，{m['out'][q] / 1e3:.1f}k token，{m['lat'][q]:.0f} 秒" if q in m["out"] else ""
        parts.append(f"{short} {res}{extra}")
    return "；".join(parts)


mac("ExampleAResult", example("abc400_c"))
mac("ExampleBResult", example("arc195_d"))
mac("ExampleCResult", example("3801"))
trunc = sum(n for m in ms for f, n in m["finish"].items() if f != "stop")
mac("TruncNote", "全部回答正常结束（finish\\_reason=stop），无截断" if trunc == 0 else f"{trunc} 个回答未正常结束")
open(os.path.join(HERE, "data.tex"), "w").write("\n".join(L) + "\n")
for (k, name, *_), m in zip(MODELS, ms):
    print(name, sum(m["passed"].values()), "answered", len(m["by_q"]), "cost", round(m["cost"], 2),
          "wall", round(m["wall"]), "served", dict(m["served"]), "errors", len(m["errors"]), file=sys.stderr)
