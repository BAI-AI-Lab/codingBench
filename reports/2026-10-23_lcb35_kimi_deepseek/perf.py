"""Measure CPU time and peak memory of every passing LiveCodeBench answer on the official tests.

Each run is a fresh python subprocess pinned to one core; CPU time and peak RSS come from the child's rusage
(os.wait4). AtCoder answers read the test from stdin; LeetCode answers are called as Solution().<fn>(*args) with
only the call timed. Every output is checked, so only correct runs count. Each (problem, test) is run REPS times
per model with the model order rotated each rep. Usage (as bench, LCB venv python):
  python perf.py <out.jsonl> <passing.json>     # passing.json: {"model": ["qid", ...]}
"""
import json
import math
import multiprocessing as mp
import os
import sys
import tempfile
import time

CB = "/data/hx/code_bench"
sys.path.insert(0, f"{CB}/src/LiveCodeBench")
PY = f"{CB}/venvs/livecodebench/bin/python"
MODELS = ["kimi-k3.1-pro", "deepseek-flash", "deepseek-v4-pro"]
REPS, WORKERS, TIMEOUT = 3, 6, 20
CORES = [200 + i for i in range(WORKERS)]  # fixed cores, away from the low ones other jobs tend to use

LC_RUNNER = r'''
import json, resource, sys, time
IMPORTS = __IMPORTS__
code, fn, inp_path, out_path = sys.argv[1:5]
ns = {}
exec(compile(IMPORTS + "\n\n" + open(code).read(), code, "exec"), ns)
method = getattr(ns["Solution"](), fn) if "Solution" in ns else ns[fn]
args = [json.loads(line) for line in open(inp_path).read().split("\n")]
c0, w0 = time.process_time(), time.perf_counter()
res = method(*args)
c1, w1 = time.process_time(), time.perf_counter()
if isinstance(res, tuple):
    res = list(res)
json.dump({"res": res, "call_cpu": c1 - c0, "call_wall": w1 - w0}, open(out_path, "w"))
'''


def cubes_exists(n):
    d = 1
    while d * d * d < n:
        if n % d == 0:
            m = n // d
            disc = 9 * d * d - 12 * (d * d - m)
            if disc >= 0:
                s = math.isqrt(disc)
                if s * s == disc and (s - 3 * d) > 0 and (s - 3 * d) % 6 == 0:
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
    gi = wi = 0

    def nxt(lines, i):
        while i < len(lines) and not lines[i].strip():
            i += 1
        return (lines[i].strip() if i < len(lines) else None), i + 1

    for r, b in cases:
        e, wi = nxt(ref, wi)
        if e == "Yes":
            wi += r + b
        g, gi = nxt(got, gi)
        if g != e:
            return False
        if g == "No":
            continue
        pts = []
        for _ in range(r + b):
            line, gi = nxt(got, gi)
            if line is None:
                return False
            p, rr, cc = line.split()
            pts.append((p, int(rr), int(cc)))
        if [p for p, _, _ in pts].count("R") != r or len({(x, y) for _, x, y in pts}) != len(pts):
            return False
        for i, (p, x, y) in enumerate(pts):
            _, x2, y2 = pts[(i + 1) % len(pts)]
            dx, dy = abs(x - x2), abs(y - y2)
            if not (1 <= x <= 10 ** 9 and 1 <= y <= 10 ** 9) or (p == "R" and dx + dy != 1) or (p == "B" and (dx, dy) != (1, 1)):
                return False
    return True


CHECK = {"abc397_d": check_cubes, "arc195_c": check_pieces}


LAUNCHER = r'''
import json, os, signal, sys, time
timeout, stdin_path, stdout_path, argv = float(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
t0 = time.perf_counter()
pid = os.fork()
if pid == 0:
    fi, fo = os.open(stdin_path, os.O_RDONLY), os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    os.dup2(fi, 0); os.dup2(fo, 1); os.dup2(os.open(os.devnull, os.O_WRONLY), 2)
    os.execv(argv[0], argv)
timed_out = []
def kill(*_):
    timed_out.append(1); os.kill(pid, 9)
signal.signal(signal.SIGALRM, kill)
signal.setitimer(signal.ITIMER_REAL, timeout)
_, status, ru = os.wait4(pid, 0)
wall = time.perf_counter() - t0
signal.setitimer(signal.ITIMER_REAL, 0)
print(json.dumps({"cpu": ru.ru_utime + ru.ru_stime, "wall": wall, "rss_kb": ru.ru_maxrss, "status": status,
                  "timeout": bool(timed_out)}))
'''
BASEPY = f"{CB}/python/cpython-3.11.17-linux-x86_64-gnu/bin/python3.11"


def run(argv, stdin_path, stdout_path, launcher):
    """Run argv through a small launcher (fresh -I -S interpreter, a few MB), so the measured child is not a fork
    of this big process; returns (cpu s, wall s, peak RSS KB, exit status) or None on timeout. The core
    affinity of the worker is inherited by the launcher and the child."""
    import subprocess
    p = subprocess.run([BASEPY, "-I", "-S", launcher, str(TIMEOUT), stdin_path, stdout_path, *argv],
                       capture_output=True, text=True)
    r = json.loads(p.stdout)
    return None if r["timeout"] else (r["cpu"], r["wall"], r["rss_kb"], r["status"])


def worker(job):
    core, qids, codes, tests, out_path, tmp = job
    os.sched_setaffinity(0, {core})
    launcher = os.path.join(tmp, "launcher.py")
    lines = []
    empty = os.path.join(tmp, f"empty_{core}.py")
    open(empty, "w").write("pass\n")
    nul_in = os.path.join(tmp, f"nul_{core}.txt")
    open(nul_in, "w").write("")
    for rep in range(20):  # startup baseline on this core
        cpu, wall, rss, _ = run([PY, empty], nul_in, os.devnull, launcher)
        lines.append({"model": "baseline", "q": "-", "test": 0, "rep": rep, "core": core, "cpu": cpu, "wall": wall,
                      "rss_kb": rss, "ok": True})
    for q in qids:
        io = tests[q]
        fn = io.get("fn_name")
        for ti, (inp, exp) in enumerate(zip(io["inputs"], io["outputs"])):
            inp_path = os.path.join(tmp, f"in_{core}.txt")
            open(inp_path, "w").write(inp)
            for rep in range(REPS):
                order = MODELS[rep % 3:] + MODELS[:rep % 3]
                for model in order:
                    if q not in codes.get(model, {}):
                        continue
                    code_path = codes[model][q]
                    out_path_ = os.path.join(tmp, f"out_{core}.txt")
                    rec = {"model": model, "q": q, "test": ti, "rep": rep, "core": core}
                    if fn:
                        r = run([PY, os.path.join(tmp, "lc_runner.py"), code_path, fn, inp_path, out_path_],
                                os.devnull, os.devnull, launcher)
                    else:
                        r = run([PY, code_path], inp_path, out_path_, launcher)
                    if r is None:
                        rec.update(ok=False, kind="TLE")
                    else:
                        cpu, wall, rss, status = r
                        rec.update(cpu=cpu, wall=wall, rss_kb=rss)
                        if status != 0:
                            rec.update(ok=False, kind="RE")
                        elif fn:
                            got = json.load(open(out_path_))
                            rec.update(ok=got["res"] == json.loads(exp), call_cpu=got["call_cpu"],
                                       call_wall=got["call_wall"])
                        else:
                            out = open(out_path_).read()
                            rec.update(ok=CHECK[q](inp, out, exp) if q in CHECK else out.split() == exp.split())
                    lines.append(rec)
        fd = os.open(out_path, os.O_WRONLY | os.O_APPEND)  # one write per problem, so workers don't interleave
        os.write(fd, "".join(json.dumps(x) + "\n" for x in lines).encode())
        os.close(fd)
        lines = []
        print(f"core {core} done {q}", flush=True)
    return core


def main():
    out_path, passing_path = sys.argv[1:3]
    import datasets
    _load = datasets.load_dataset
    datasets.load_dataset = lambda path, *a, **k: _load(
        f"{CB}/data/code_generation_lite" if path == "livecodebench/code_generation_lite" else path, *a, **k)
    from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
    from lcb_runner.evaluation.testing_util import import_string

    passing = json.load(open(passing_path))
    want = {q for qs in passing.values() for q in qs}
    tests = {p.question_id: json.loads(p.get_evaluation_sample()["input_output"])
             for p in load_code_generation_dataset("release_v6") if p.question_id in want}
    tmp = tempfile.mkdtemp(prefix="perf_")
    open(os.path.join(tmp, "lc_runner.py"), "w").write(LC_RUNNER.replace("__IMPORTS__", repr(import_string)))
    open(os.path.join(tmp, "launcher.py"), "w").write(LAUNCHER)
    codes = {}
    for model, qs in passing.items():
        run_file = f"{CB}/runs/{model}/livecodebench-lcb_newest35-full/output/{model}/Scenario.codegeneration_1_0.2_eval_all.json"
        recs = {r["question_id"]: r for r in json.load(open(run_file))}
        for q in qs:
            path = os.path.join(tmp, f"{model}__{q}.py")
            open(path, "w").write(recs[q]["code_list"][0])
            codes.setdefault(model, {})[q] = path
    # longest-first assignment of problems to workers, by total input bytes
    load = sorted(want, key=lambda q: -sum(map(len, tests[q]["inputs"])))
    buckets = [[] for _ in range(WORKERS)]
    weight = [0] * WORKERS
    for q in load:
        i = weight.index(min(weight))
        buckets[i].append(q)
        weight[i] += sum(map(len, tests[q]["inputs"])) + 2000 * len(tests[q]["inputs"])
    open(out_path, "w").close()
    jobs = [(CORES[i], buckets[i], codes, tests, out_path, tmp) for i in range(WORKERS)]
    with mp.Pool(WORKERS) as pool:
        for core in pool.imap_unordered(worker, jobs):
            print(f"core {core} finished", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
