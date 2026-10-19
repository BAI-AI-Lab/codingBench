"""Markdown report for a finished LiveCodeBench run.

  python lcb_report.py <run dir, e.g. runs/<model>/livecodebench-...-full> [--out report.md] [--compare <run dir> --compare-label 64k]

Breaks pass@1 down by difficulty, platform and month, and sorts failures by what the judge saw.
"""
import argparse
import collections
import glob
import json
import os
import statistics

ERR = {-2: "答案错误", -3: "超时", -4: "运行错误或编译失败", -1: "其他错误"}

ap = argparse.ArgumentParser()
ap.add_argument("run_dir")
ap.add_argument("--out")
ap.add_argument("--compare", help="an earlier run of the same problems (e.g. with a smaller MAX_TOKENS)")
ap.add_argument("--label", default="本次", help="name of this run in the comparison")
ap.add_argument("--compare-label", default="对比", help="name of the --compare run")
a = ap.parse_args()


def load(run_dir):
    f = glob.glob(os.path.join(run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if len(f) != 1:
        raise SystemExit(f"expected one *_eval_all.json under {run_dir}/output, found {len(f)}")
    return f, json.load(open(f[0]))


f, rows = load(a.run_dir)
model = json.load(open(os.path.join(a.run_dir, "result.json")))["model"] if os.path.exists(
    os.path.join(a.run_dir, "result.json")) else os.path.basename(os.path.dirname(f[0]))


def passed(r):
    return bool(r["graded_list"][0])


def why(r):
    if passed(r):
        return None
    if not r["code_list"][0].strip() or r["code_list"][0].strip() == "# YOUR CODE HERE":
        return "没有给出代码"
    try:
        md = json.loads(r["metadata"][0])
    except (ValueError, IndexError, TypeError):
        return "其他错误"
    return ERR.get(md.get("error_code"), "其他错误")


def table(key, order=None):
    g = collections.defaultdict(list)
    for r in rows:
        g[key(r)].append(passed(r))
    ks = order or sorted(g)
    out = ["| | 题数 | 通过 | pass@1 |", "|---|---:|---:|---:|"]
    for k in ks:
        if k in g:
            v = g[k]
            out.append(f"| {k} | {len(v)} | {sum(v)} | {100 * sum(v) / len(v):.1f}% |")
    return "\n".join(out)


n, ok = len(rows), sum(passed(r) for r in rows)
dates = sorted(r["contest_date"][:10] for r in rows)
lens = [len(r["output_list"][0]) for r in rows]
fails = collections.Counter(why(r) for r in rows if not passed(r))
md = [f"# LiveCodeBench 报告：{model}", "",
      f"- 题目：{n} 题，发布日期 {dates[0]} 到 {dates[-1]}（LiveCodeBench release_v6 中最新的 {n} 题）",
      f"- 设置：每题 1 次，temperature 0.2，官方提示词和官方判题程序",
      "", f"## 总分：pass@1 = **{100 * ok / n:.1f}%**（{ok}/{n}）", "",
      "## 按难度", "", table(lambda r: r["difficulty"], ["easy", "medium", "hard"]), "",
      "## 按来源", "", table(lambda r: r["platform"]), "",
      "## 按月份", "", table(lambda r: r["contest_date"][:7]), "",
      "## 没通过的原因", "", "| 原因 | 题数 |", "|---|---:|"]
md += [f"| {k} | {v} |" for k, v in fails.most_common()]
if a.compare:
    _, old = load(a.compare)
    old = {r["question_id"]: r for r in old}
    same = [r for r in rows if r["question_id"] in old]
    if len(same) != len(rows):
        raise SystemExit("--compare run has different problems")
    ok_old = sum(passed(old[r["question_id"]]) for r in rows)
    md += ["", f"## {a.compare_label} 和 {a.label} 对比", "",
           f"- {a.compare_label}：{ok_old}/{n}（{100 * ok_old / n:.1f}%）",
           f"- {a.label}：{ok}/{n}（{100 * ok / n:.1f}%）", ""]
    diff = [r for r in rows if passed(r) != passed(old[r["question_id"]]) or why(r) != why(old[r["question_id"]])]
    if diff:
        md += ["| 题号 | 难度 | " + a.compare_label + " | " + a.label + " |", "|---|---|---|---|"]
        md += [f"| {r['question_id']} | {r['difficulty']} | {'通过' if passed(old[r['question_id']]) else why(old[r['question_id']])} | "
               f"{'通过' if passed(r) else why(r)} |" for r in diff]
    else:
        md.append("两次结果完全相同。")
md += ["", "## 回答长度（字符数，只算最终回答，不含思考过程）", "",
       f"中位数 {statistics.median(lens):.0f}，最长 {max(lens)}，最短 {min(lens)}", "",
       "## 每道题", "", "| 题号 | 日期 | 来源 | 难度 | 结果 |", "|---|---|---|---|---|"]
for r in sorted(rows, key=lambda r: (r["contest_date"], r["question_id"]), reverse=True):
    md.append(f"| {r['question_id']} | {r['contest_date'][:10]} | {r['platform']} | {r['difficulty']} | "
              f"{'通过' if passed(r) else why(r)} |")
text = "\n".join(md) + "\n"
out = a.out or os.path.join(a.run_dir, "report.md")
open(out, "w").write(text)
print(text[:1500])
print(f"... written to {out}")
