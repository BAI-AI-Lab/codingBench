"""tools/lcb_report.py on a hand-made LiveCodeBench result: totals, per-difficulty rows and failure reasons.

  python tests/test_lcb_report.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def row(qid, date, diff, platform, ok, code="print(1)", meta=None, out="```python\nprint(1)\n```"):
    return {"question_id": qid, "contest_date": date + "T00:00:00", "difficulty": diff, "platform": platform,
            "graded_list": [ok], "code_list": [code], "output_list": [out],
            "metadata": [json.dumps(meta or {})], "question_content": "..."}


rows = [row("a1", "2025-04-06", "easy", "atcoder", True),
        row("a2", "2025-04-05", "hard", "atcoder", False, meta={"error_code": -2, "error_message": "Wrong Answer"}),
        row("l1", "2025-03-01", "medium", "leetcode", False, meta={"error_code": -3}),
        row("l2", "2025-03-02", "hard", "leetcode", False, code="", out=""),
        row("l3", "2025-03-03", "medium", "leetcode", True)]

with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "output", "m"))
    json.dump(rows, open(os.path.join(d, "output", "m", "Scenario.codegeneration_1_0.2_eval_all.json"), "w"))
    json.dump({"model": "m"}, open(os.path.join(d, "result.json"), "w"))
    subprocess.run([sys.executable, os.path.join(HERE, "..", "tools", "lcb_report.py"), d], check=True,
                   stdout=subprocess.DEVNULL)
    rep = open(os.path.join(d, "report.md")).read()
    # the same problems again with l2 now answered: --compare lists exactly that change
    d2 = os.path.join(d, "second")
    os.makedirs(os.path.join(d2, "output", "m"))
    rows2 = [dict(r) for r in rows]
    rows2[3] = row("l2", "2025-03-02", "hard", "leetcode", True)
    json.dump(rows2, open(os.path.join(d2, "output", "m", "Scenario.codegeneration_1_0.2_eval_all.json"), "w"))
    subprocess.run([sys.executable, os.path.join(HERE, "..", "tools", "lcb_report.py"), d2, "--compare", d,
                    "--label", "256k", "--compare-label", "64k"], check=True, stdout=subprocess.DEVNULL)
    rep2 = open(os.path.join(d2, "report.md")).read()

checks = {
    "total": "pass@1 = **40.0%**（2/5）" in rep,
    "easy row": "| easy | 1 | 1 | 100.0% |" in rep,
    "hard row": "| hard | 2 | 0 | 0.0% |" in rep,
    "medium row": "| medium | 2 | 1 | 50.0% |" in rep,
    "platform": "| leetcode | 3 | 1 | 33.3% |" in rep,
    "month": "| 2025-03 | 3 | 1 | 33.3% |" in rep,
    "wrong answer": "| 答案错误 | 1 |" in rep,
    "timeout": "| 超时 | 1 |" in rep,
    "empty answer": "| 没有给出代码 | 1 |" in rep,
    "newest first": rep.index("| a1 |") < rep.index("| l1 |"),
    "compare totals": "- 64k：2/5（40.0%）" in rep2 and "- 256k：3/5（60.0%）" in rep2,
    "compare lists only the change": "| l2 | hard | 没有给出代码 | 通过 |" in rep2 and "| a2 | hard | 答案错误" not in rep2,
}
for k, v in checks.items():
    print(("ok   " if v else "FAIL ") + k)
sys.exit(0 if all(checks.values()) else 1)
