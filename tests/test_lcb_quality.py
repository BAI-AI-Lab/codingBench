"""Parsers and tables of tools/lcb_quality.py on canned Pylint/Radon outputs (no Pylint or Radon needed).

  python tests/test_lcb_quality.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from lcb_quality import parse_pylint, parse_radon, summarize  # noqa: E402

msg = lambda t, mid: {"type": t, "messageId": mid, "symbol": "x"}
pl = parse_pylint(json.dumps({"messages": [msg("convention", "C0114"), msg("error", "E0602")],
                              "statistics": {"messageTypeCount": {"convention": 5, "error": 1, "warning": 0, "refactor": 0,
                                                                  "fatal": 0, "info": 0}, "score": 2.31}}))
assert {k: v for k, v in pl.items() if k != "messages"} == {"convention": 5, "refactor": 0, "warning": 0, "error": 1,
                                                          "fatal": 0, "total": 6, "score": 2.31}, pl
assert pl["messages"] == {"C0114 x": 1, "E0602 x": 1}, pl
bad = parse_pylint(json.dumps({"messages": [msg("error", "E0001")],
                               "statistics": {"messageTypeCount": {"error": 1}, "score": 0}}))
assert bad["score"] is None and bad["error"] == 1  # a file that does not parse gets no score
# radon cc -j lists a class and, again, each of its methods; the paper sums every entry
cc = {"a.py": [{"type": "class", "complexity": 4, "methods": [{"complexity": 3}]}, {"type": "method", "complexity": 3},
               {"type": "function", "complexity": 2}]}
ra = parse_radon(json.dumps(cc), json.dumps({"a.py": {"mi": 64.7}}),
                 json.dumps({"a.py": {"loc": 16, "lloc": 13, "sloc": 13, "comments": 1, "multi": 0, "blank": 3}}))
assert ra == {"complexity": 9, "functions": 3, "mi": 64.7, "loc": 16, "lloc": 13, "sloc": 13, "comments": 1, "blank": 3}, ra
script = parse_radon("{}", json.dumps({"a.py": {"mi": 70.5}}),
                     json.dumps({"a.py": {"loc": 13, "lloc": 6, "sloc": 10, "comments": 0, "multi": 0, "blank": 3}}))
assert script["complexity"] == 0 and script["functions"] == 0 and script["sloc"] == 10, script  # no functions at all
assert parse_radon(json.dumps({"a.py": {"error": "x"}}), json.dumps({"a.py": {"error": "x"}}),
                   json.dumps({"a.py": {"error": "x"}})) is None
recs = [{"q": "a", "difficulty": "hard", "passed": True, "pylint": pl, "radon": ra, "sonar": None},
        {"q": "b", "difficulty": "hard", "passed": False, "pylint": pl, "radon": dict(ra, sloc=7), "sonar": None}]
md = summarize(recs, sonar_on=False)
assert "| hard | 2 |" in md and "| hard | 1 | 13 | 46.15 |" in md, md  # 6 issues / 13 SLOC x 100
assert "| Pylint score ↑ | CC ↓ | MI ↑ | Func | LOC |" in md, md  # direction marks; size columns get none
print("ok")
