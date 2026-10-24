"""Re-judge a finished LiveCodeBench run with real stdin/stdout and, where any valid answer is accepted, a checker.

  python lcb_rejudge.py <run dir, e.g. runs/<model>/livecodebench-...-full> [--workers 16] [--timeout 6]

LCB's own judge runs AtCoder answers in-process with a mocked stdin whose buffer.readline always returns the first
line, and with stdout replaced by a StringIO (no sys.stdout.buffer), so correct programs that read or write that way
fail. Here every AtCoder answer runs as its own Python process (the LCB env's python) on all official tests, and the
output is compared token by token, except:
  abc397_d  x^3 - y^3 = N: any positive (x, y) is correct, and -1 only when none exists (test 41's reference "3 0"
            is itself invalid: y = 0 is not positive)
  arc195_c  Hamiltonian Pieces: any valid placement is correct; Yes/No must match the reference
LeetCode answers are function calls, untouched by those problems, and keep LCB's verdict.
Writes <run dir>/rejudge.jsonl (one line per problem) and prints pass@1 before and after.
"""
import argparse
import concurrent.futures
import glob
import json
import math
import os
import subprocess
import sys
import tempfile


def cubes_exists(n):  # positive x, y with x^3 - y^3 = n; d = x - y divides n and d^3 < n
    d = 1
    while d * d * d < n:
        if n % d == 0:
            disc = 9 * d * d - 12 * (d * d - n // d)  # 3y^2 + 3dy + d^2 = n / d
            if disc >= 0:
                s = math.isqrt(disc)
                if s * s == disc and s - 3 * d > 0 and (s - 3 * d) % 6 == 0:
                    return True
        d += 1
    return False


def check_cubes(inp, out, exp):
    n, t = int(inp.split()[0]), out.split()
    if t == ["-1"]:
        return not cubes_exists(n)
    if len(t) != 2:
        return False
    x, y = map(int, t)
    return x > 0 and y > 0 and x ** 3 - y ** 3 == n


def check_pieces(inp, out, exp):
    it = iter(inp.split())
    cases = [(int(next(it)), int(next(it))) for _ in range(int(next(it)))]
    got, ref = out.split("\n"), exp.split("\n")
    gi = ri = 0

    def nxt(lines, i):
        while i < len(lines) and not lines[i].strip():
            i += 1
        return (lines[i].strip() if i < len(lines) else None), i + 1

    for r, b in cases:
        e, ri = nxt(ref, ri)
        if e == "Yes":
            ri += r + b  # skip the reference placement
        g, gi = nxt(got, gi)
        if g != e:
            return False
        if g == "No":
            continue
        pts = []
        for _ in range(r + b):
            line, gi = nxt(got, gi)
            if line is None or len(line.split()) != 3:
                return False
            p, x, y = line.split()
            pts.append((p, int(x), int(y)))
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


def judge(code, tests, check, timeout):
    """Run code on every (input, expected) test; returns (passed count, [(test index, WA/RE/TLE), ...])."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
    ok, bad = 0, []
    try:
        for i, (inp, exp) in enumerate(tests):
            try:
                p = subprocess.run([sys.executable, f.name], input=inp, capture_output=True, text=True, timeout=timeout)
                if p.returncode:
                    kind = "RE"
                else:
                    kind = "ok" if (check(inp, p.stdout, exp) if check else p.stdout.split() == exp.split()) else "WA"
            except subprocess.TimeoutExpired:
                kind = "TLE"
            except (ValueError, IndexError):  # a checker could not parse the output
                kind = "WA"
            ok += kind == "ok"
            if kind != "ok":
                bad.append((i, kind))
    finally:
        os.unlink(f.name)
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", 16)))
    ap.add_argument("--timeout", type=float, default=6, help="seconds per test")
    a = ap.parse_args()
    f = glob.glob(os.path.join(a.run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if len(f) != 1:
        raise SystemExit(f"expected one *_eval_all.json under {a.run_dir}/output, found {len(f)}")
    rows = json.load(open(f[0]))

    cb = os.environ["CB"]
    sys.path.insert(0, os.path.join(cb, "src", "LiveCodeBench"))
    import datasets
    _load = datasets.load_dataset
    local = os.path.join(cb, "data", "code_generation_lite")
    datasets.load_dataset = lambda path, *x, **k: _load(local if path == "livecodebench/code_generation_lite" else path, *x, **k)
    from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
    want = {r["question_id"] for r in rows if r["platform"] == "atcoder"}
    release = os.environ.get("LCB_RELEASE", "release_v6")
    tests = {p.question_id: json.loads(p.get_evaluation_sample()["input_output"])
             for p in load_code_generation_dataset(release) if p.question_id in want}

    out = {}
    with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
        jobs = {}
        for r in rows:
            q, lcb = r["question_id"], bool(r["graded_list"][0])
            rec = {"q": q, "platform": r["platform"], "difficulty": r["difficulty"], "lcb": lcb}
            if r["platform"] != "atcoder":
                out[q] = {**rec, "passed": lcb, "how": "LCB (function call)"}
            elif not r["code_list"][0].strip():
                out[q] = {**rec, "passed": False, "how": "no code"}
            else:
                io = tests[q]
                jobs[pool.submit(judge, r["code_list"][0], list(zip(io["inputs"], io["outputs"])), CHECK.get(q),
                                 a.timeout)] = (q, rec, len(io["inputs"]))
        for fut in concurrent.futures.as_completed(jobs):
            q, rec, n = jobs[fut]
            ok, bad = fut.result()
            out[q] = {**rec, "passed": ok == n, "how": ("checker" if q in CHECK else "exact"), "tests": f"{ok}/{n}",
                      "failed_tests": bad[:5]}
            print(f"  {q:<10} {out[q]['tests']:>7} {'ok' if ok == n else bad[0][1]}", flush=True)

    path = os.path.join(a.run_dir, "rejudge.jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(out[r["question_id"]]) + "\n")
    n = len(rows)
    before, after = sum(v["lcb"] for v in out.values()), sum(v["passed"] for v in out.values())
    print(f"pass@1  LCB {before}/{n} ({100 * before / n:.1f}%)  ->  re-judged {after}/{n} ({100 * after / n:.1f}%)")
    for v in sorted(out.values(), key=lambda v: v["q"]):
        if v["passed"] != v["lcb"]:
            print(f"  {v['q']}: {'fail -> pass' if v['passed'] else 'pass -> fail'} ({v['how']} {v.get('tests', '')})")
    print("written", path)


if __name__ == "__main__":
    main()
