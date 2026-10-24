"""Static metrics of every passing answer: radon raw/cyclomatic/maintainability, pyflakes warnings, AST nesting
depth and the stdin-reading style. Writes static.jsonl next to this file. Run with the scratch lint venv."""
import ast
import io
import json
import os
import re

from pyflakes.api import check
from pyflakes.reporter import Reporter
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = ["kimi-k3.1-pro", "deepseek-flash", "deepseek-v4-pro"]
passing = json.load(open(os.path.join(HERE, "..", "passing.json")))
COMPOUND = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.AsyncFor, ast.AsyncWith, ast.Match)


def depth(node, d=0):
    kids = [depth(c, d + isinstance(c, COMPOUND)) for c in ast.iter_child_nodes(node)]
    return max([d] + kids)


def io_style(code):
    if re.search(r"sys\.stdin\.buffer\.read\(\)|sys\.stdin\.buffer\.read\b(?!line)", code):
        return "buffer.read"
    if re.search(r"sys\.stdin\.read\(|open\(0\)", code):
        return "read"
    if "buffer.readline" in code:
        return "buffer.readline"
    if "sys.stdin.readline" in code:
        return "readline"
    if re.search(r"\binput\(", code):
        return "input()"
    return "函数调用"


out = []
for m in MODELS:
    rows = {r["question_id"]: r for r in json.load(open(os.path.join(HERE, "runs", m, "eval_all.json")))}
    for q in passing[m]:
        code = rows[q]["code_list"][0]
        raw = analyze(code)
        blocks = cc_visit(code)
        warn = io.StringIO()
        n_warn = check(code, q, Reporter(warn, io.StringIO()))
        tree = ast.parse(code)
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        out.append({
            "model": m, "q": q, "platform": rows[q]["platform"], "difficulty": rows[q]["difficulty"],
            "sloc": raw.sloc, "comments": raw.comments + raw.multi, "blank": raw.blank,
            "functions": len(funcs),
            "cc_total": sum(b.complexity for b in blocks) or 1,
            "cc_max": max((b.complexity for b in blocks), default=1),
            "mi": round(mi_visit(code, multi=True), 1),
            "depth": depth(tree),
            "pyflakes": n_warn, "pyflakes_msgs": [l.split(":", 2)[-1].strip() for l in warn.getvalue().splitlines()],
            "io": io_style(code),
            "recursionlimit": "setrecursionlimit" in code,
            "chars": len(code),
        })
with open(os.path.join(HERE, "static.jsonl"), "w") as f:
    f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
print(len(out), "answers")
