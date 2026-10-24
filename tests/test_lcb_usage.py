"""tools/lcb_usage.py on hand-made calls: matching, covered time, first-token times, speeds, peak pricing and tables.

  python tests/test_lcb_usage.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from lcb_usage import analyze, covered, render  # noqa: E402

assert covered([(0, 10), (5, 12), (20, 25)]) == 17  # overlapping requests count once
assert covered([(0, 10), (2, 3)]) == 10

# Monday 2026-10-19: 02:00 UTC is a DeepSeek peak hour, 12:00 UTC is not
mon = lambda h: datetime.datetime(2026, 10, 19, h, tzinfo=datetime.timezone.utc).timestamp()  # noqa: E731
rows = [{"question_id": "a", "difficulty": "easy", "platform": "atcoder", "question_content": "Add two numbers."},
        {"question_id": "b", "difficulty": "hard", "platform": "leetcode", "question_content": "Find the path."},
        {"question_id": "c", "difficulty": "hard", "platform": "atcoder", "question_content": "Count trees."}]
u = lambda out, reason=0: {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 400, "completion_tokens": out,  # noqa: E731
                           "completion_tokens_details": {"reasoning_tokens": reason}}
t0, t1 = mon(2), mon(12)
calls = [
    # a: streamed, logged with its question_id
    {"q": "a", "start": t0, "end": t0 + 20, "first_token": t0 + 2, "first_content": t0 + 15, "usage": u(1800, 1500),
     "finish": ["stop"], "content": ["x"]},
    # b: an older log without question_id, matched by the statement in the prompt; failed once, then answered
    {"start": t1, "end": t1 + 5, "error": "APITimeoutError", "messages": [{"content": "Q: Find the path."}]},
    {"start": t1 + 10, "end": t1 + 110, "usage": u(5000), "finish": ["stop"],
     "messages": [{"content": "### Question:\nFind the path.\n"}]},
]
passed = {"a": True, "b": False, "c": False}  # e.g. from rejudge.jsonl
prices = {"in": 1.0, "hit": 0.1, "out": 10.0, "off": {"in": 0.5, "hit": 0.05, "out": 5.0}, "peak_hours": [(1, 4), (6, 10)]}
s = analyze(rows, calls, passed, prices)
pa, pb, pc = s["per_problem"]
assert pa["latency"] == 20 and pa["ttft"] == 2 and pa["first_answer"] == 15 and pa["decode"] == 100 and pa["speed"] == 90, pa
assert pb["latency"] == 100 and pb["ttft"] is None and pb["out"] == 5000, pb
assert "latency" not in pc and s["missing"] == ["c"]
assert s["calls_ok"] == 2 and s["calls_error"] == 1 and s["active_s"] == 120
assert s["tokens"] == {"input": 2000, "cache_hit": 800, "output": 6800, "reasoning": 1500}, s["tokens"]
# a at the peak rate: (600 x 1 + 400 x 0.1 + 1800 x 10) / 1e6; b off-peak: (600 x 0.5 + 400 x 0.05 + 5000 x 5) / 1e6
assert abs(s["cost"] - (18640 + 25320) / 1e6) < 1e-12 and s["cost_per_pass"] == s["cost"], s["cost"]
assert s["ttft"]["n"] == 1 and s["latency"]["n"] == 2
md = render(s, "m", "按 cb rejudge 复核")
assert "通过 1（pass@1 33.3%" in md and "| 总延迟 ↓ | 2 |" in md and "| 首个 token ↓ | 1 |" in md, md
assert "| 难度 | 题数 | 通过 ↑ | 延迟中位数（秒）↓ |" in md and "| c | hard | ✗ | — |" in md, md
assert "其中思考 1.5k，占 22%" in md and "高峰（UTC 周一至周五 01:00–04:00、06:00–10:00）" in md, md
flat = analyze(rows, calls, passed, {"in": 1.0, "hit": 0.1, "out": 10.0})
assert abs(flat["cost"] - (18640 + 50640) / 1e6) < 1e-12  # one price at any time
assert "cost" not in analyze(rows, calls, passed, None)
print("ok")
