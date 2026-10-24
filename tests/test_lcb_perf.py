"""Tables of tools/lcb_perf.py on hand-made measurements (nothing is run).

  python tests/test_lcb_perf.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from lcb_perf import compare, render_compare, render_run, summarize  # noqa: E402

rows = [{"model": "baseline", "q": "-", "test": 0, "rep": i, "cpu": c, "rss_kb": 12000, "ok": True}
        for i, c in enumerate([0.025, 0.026, 0.027])]


def run(m, q, test, cpu, rss=20000, ok=True, call=None):
    for rep, d in enumerate((0.0, 0.01, -0.01)):  # three reps around cpu
        r = {"model": m, "q": q, "test": test, "rep": rep, "cpu": cpu + d, "rss_kb": rss, "ok": ok}
        if call is not None:
            r["call_cpu"] = call + d
        rows.append(r)


run("A", "big", 0, 0.026 + 0.5)        # AtCoder: net = process CPU - baseline 0.026
run("A", "big", 1, 0.026 + 0.2, rss=50000)
run("B", "big", 0, 0.026 + 1.5)
run("B", "big", 1, 0.026 + 0.1)
run("A", "lc", 0, 0.05, call=0.3)      # LeetCode: only the call counts
run("B", "lc", 0, 0.05, call=0.2)
run("A", "tiny", 0, 0.03)              # below the 0.1 s threshold for both: not compared
run("B", "tiny", 0, 0.03)
run("B", "wrong", 0, 2.0, ok=False)    # a wrong output drops that answer
s = summarize(rows)
assert abs(s["baseline_cpu"] - 0.026) < 1e-12 and s["failed"] == [("B", "wrong")]
big = s["problems"]["big"]
assert abs(big["A"]["max_cpu"] - 0.5) < 1e-9 and abs(big["A"]["total_cpu"] - 0.7) < 1e-9 and big["A"]["rss_kb"] == 50000
assert abs(big["B"]["max_cpu"] - 1.5) < 1e-9 and big["A"]["tests"] == 2
assert abs(s["problems"]["lc"]["B"]["max_cpu"] - 0.2) < 1e-9 and "wrong" not in s["problems"]
c = compare(s, ["A", "B"])
assert c["measurable"] == ["big", "lc"] and c["common"] == ["big", "lc"], c
# A: big 0.5/0.5 = 1, lc 0.3/0.2 = 1.5 -> sqrt(1.5); B: big 3, lc 1 -> sqrt(3)
assert abs(c["models"]["A"]["geo_mean"] - 1.5 ** 0.5) < 1e-9 and abs(c["models"]["B"]["geo_mean"] - 3 ** 0.5) < 1e-9
assert c["models"]["A"]["fastest"] == 1 and c["models"]["B"]["slow2"] == 1
meta = {q: {"difficulty": "hard", "platform": "atcoder"} for q in ("big", "lc", "tiny", "wrong")}
md = render_compare(s, c, ["A", "B"], meta)
assert "| 运行 | 相对最快倍数（几何平均）↓ | 最快（题）↑ |" in md and "| big | hard | **0.50** | 1.50（3.0×） |" in md, md
one = render_run(s, "B", meta)
assert "不计入：wrong" in one and "| big | hard | atcoder | 2 | 1.500 |" in one and "最慢测试 CPU（秒）↓" in one, one
print("ok")
