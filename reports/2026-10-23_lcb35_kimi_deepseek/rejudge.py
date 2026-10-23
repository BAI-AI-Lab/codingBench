"""Re-judge with real stdin/stdout and, for problems that accept any valid answer, a checker instead of an exact
match: abc397_d (x^3 - y^3 = N) and arc195_c (Hamiltonian Pieces). Usage: python rejudge.py <model>:<qid> ...
Also prints abc397_d tests whose expected output is itself invalid.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

CB = "/data/hx/code_bench"
sys.path.insert(0, f"{CB}/src/LiveCodeBench")
import datasets  # noqa: E402

_load = datasets.load_dataset
datasets.load_dataset = lambda path, *a, **k: _load(
    f"{CB}/data/code_generation_lite" if path == "livecodebench/code_generation_lite" else path, *a, **k)
from lcb_runner.benchmarks.code_generation import load_code_generation_dataset  # noqa: E402

PY = f"{CB}/venvs/livecodebench/bin/python"
want = [a.split(":") for a in sys.argv[1:]]
probs = {p.question_id: p for p in load_code_generation_dataset("release_v6") if p.question_id in {q for _, q in want}}


def cubes_exists(n):  # positive x, y with x^3 - y^3 = n; d = x - y divides n and d^3 < n
    d = 1
    while d * d * d < n:
        if n % d == 0:
            m = n // d  # 3y^2 + 3dy + d^2 = m
            disc = 9 * d * d - 12 * (d * d - m)
            if disc >= 0:
                s = math.isqrt(disc)
                if s * s == disc and (s - 3 * d) > 0 and (s - 3 * d) % 6 == 0:
                    return True
        d += 1
    return False


def check_cubes(inp, out, exp):
    n = int(inp.split()[0])
    t = out.split()
    if t == ["-1"]:
        return not cubes_exists(n)
    if len(t) != 2:
        return False
    x, y = map(int, t)
    return x > 0 and y > 0 and x ** 3 - y ** 3 == n


def check_pieces(inp, out, exp):
    it = iter(inp.split())
    cases = [(int(next(it)), int(next(it))) for _ in range(int(next(it)))]
    got, want_ = out.split("\n"), exp.split("\n")
    gi = wi = 0

    def nxt(lines, i):
        while i < len(lines) and not lines[i].strip():
            i += 1
        return (lines[i].strip() if i < len(lines) else None), i + 1

    for r, b in cases:
        e, wi = nxt(want_, wi)
        if e == "Yes":
            wi += r + b  # skip the reference placement
        g, gi = nxt(got, gi)
        if g != e:
            return False  # Yes/No must agree with the reference (it decides feasibility)
        if g == "No":
            continue
        pts = []
        for _ in range(r + b):
            line, gi = nxt(got, gi)
            if line is None:
                return False
            p, rr, cc = line.split()
            pts.append((p, int(rr), int(cc)))
        if [p for p, _, _ in pts].count("R") != r or [p for p, _, _ in pts].count("B") != b:
            return False
        if len({(x, y) for _, x, y in pts}) != len(pts) or not all(1 <= x <= 10 ** 9 and 1 <= y <= 10 ** 9 for _, x, y in pts):
            return False
        for i, (p, x, y) in enumerate(pts):
            _, x2, y2 = pts[(i + 1) % len(pts)]
            dx, dy = abs(x - x2), abs(y - y2)
            if (p == "R" and dx + dy != 1) or (p == "B" and (dx, dy) != (1, 1)):
                return False
    return True


CHECK = {"abc397_d": check_cubes, "arc195_c": check_pieces}

if "abc397_d" in probs:
    io = json.loads(probs["abc397_d"].get_evaluation_sample()["input_output"])
    for i, (inp, exp) in enumerate(zip(io["inputs"], io["outputs"])):
        if not check_cubes(inp, exp, exp):
            print(json.dumps({"bad_reference": "abc397_d", "test": i, "input": inp.strip(), "expected": exp.strip(),
                              "positive_solution_exists": cubes_exists(int(inp.split()[0]))}))

for model, q in want:
    run = f"{CB}/runs/{model}/livecodebench-lcb_newest35-full/output/{model}/Scenario.codegeneration_1_0.2_eval_all.json"
    rec = {r["question_id"]: r for r in json.load(open(run))}[q]
    io = json.loads(probs[q].get_evaluation_sample()["input_output"])
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(rec["code_list"][0])
    ok, bad = 0, []
    for i, (inp, exp) in enumerate(zip(io["inputs"], io["outputs"])):
        try:
            p = subprocess.run([PY, f.name], input=inp, capture_output=True, text=True, timeout=6)
            good = p.returncode == 0 and (CHECK[q](inp, p.stdout, exp) if q in CHECK else p.stdout.split() == exp.split())
            kind = "ok" if good else ("RE" if p.returncode else "WA")
        except subprocess.TimeoutExpired:
            kind = "TLE"
        ok += kind == "ok"
        if kind != "ok":
            bad.append((i, kind))
    os.unlink(f.name)
    print(json.dumps({"model": model, "q": q, "lcb": "pass" if rec["graded_list"][0] else "fail",
                      "checker" if q in CHECK else "exact": f"{ok}/{len(io['inputs'])}", "failed_tests": bad[:5]}))
