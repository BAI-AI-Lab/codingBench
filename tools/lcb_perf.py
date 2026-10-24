"""CPU time and peak memory of the passing answers of one or more LiveCodeBench runs, on the official tests.

  python lcb_perf.py <run dir> [<run dir> ...] [--reps 3] [--workers 6] [--timeout 20] [--out compare.md]

Every run is a fresh Python process (the LCB env's python) pinned to one core; CPU time and peak RSS come from the
child's rusage (os.wait4), through a small `python -I -S` launcher, so the measured child is not a fork of this big
process (a fork of it inflates rusage CPU by ~0.2 s and maxrss by GBs). AtCoder answers read the test from stdin
(CPU = process CPU minus the startup baseline, an empty program measured 20 times per core); LeetCode answers are
called as Solution().<fn>(*args) and only the call is timed. Every output is checked (abc397_d and arc195_c with the
checkers of cb rejudge); a wrong or failed run drops that answer from the tables. Each (problem, test) runs --reps
times per answer, with the order of the runs rotated each rep, and the median counts.

Passing answers come from <run dir>/rejudge.jsonl (cb rejudge) when it exists, else LCB's verdict. Writes, in every
run dir, perf.jsonl (each measured run) and perf.md / perf.json (per problem: slowest test, all tests, peak memory).
With several run dirs they are measured together, interleaved, and the comparison is printed (and written to --out):
only problems whose slowest answer needs at least 0.1 s of CPU beyond startup are compared, since below that the
startup dominates.
"""
import argparse
import collections
import glob
import json
import math
import multiprocessing as mp
import os
import statistics
import subprocess
import sys
import tempfile

THRESH = 0.1  # s of CPU above the startup baseline for the slowest answer before a problem is compared
LEGEND = "↑ 越大越好，↓ 越小越好；没有箭头的只作描述。"

LC_RUNNER = r'''
import json, sys, time
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


# ---------------------------------------------------------------- tables (no measuring; tests/test_lcb_perf.py)

def summarize(rows):
    """perf.jsonl records (any number of models) -> baseline and, per problem and model, the medians over reps:
    {"baseline_cpu", "baseline_rss_kb", "problems": {q: {model: {max_cpu, total_cpu, rss_kb, tests}}}, "failed"}."""
    base = [r for r in rows if r["model"] == "baseline"]
    b_cpu = statistics.median(r["cpu"] for r in base)
    per, failed = collections.defaultdict(list), set()
    for r in rows:
        if r["model"] == "baseline":
            continue
        if not r.get("ok"):
            failed.add((r["model"], r["q"]))
            continue
        net = r["call_cpu"] if "call_cpu" in r else max(0.0, r["cpu"] - b_cpu)
        per[(r["model"], r["q"], r["test"])].append((net, r["rss_kb"]))
    probs = collections.defaultdict(dict)
    for (m, q, _), v in sorted(per.items()):
        if (m, q) in failed:
            continue
        c, rss = statistics.median(x[0] for x in v), statistics.median(x[1] for x in v)
        a = probs[q].setdefault(m, {"max_cpu": 0.0, "total_cpu": 0.0, "rss_kb": 0, "tests": 0})
        a["max_cpu"], a["total_cpu"], a["rss_kb"], a["tests"] = max(a["max_cpu"], c), a["total_cpu"] + c, \
            max(a["rss_kb"], rss), a["tests"] + 1
    return {"baseline_cpu": b_cpu, "baseline_rss_kb": statistics.median(r["rss_kb"] for r in base),
            "problems": dict(probs), "failed": sorted(failed)}


def compare(s, models, thresh=THRESH):
    """Problems every model answered and some answer needs >= thresh s; per model the ratio to the fastest."""
    probs = s["problems"]
    measurable = sorted(q for q, d in probs.items() if max(v["max_cpu"] for v in d.values()) >= thresh)
    common = [q for q in measurable if all(m in probs[q] for m in models)]
    agg = {}
    for m in models:
        ratios = [probs[q][m]["max_cpu"] / max(1e-3, min(probs[q][x]["max_cpu"] for x in models)) for q in common]
        agg[m] = {"geo_mean": math.exp(statistics.mean(map(math.log, ratios))) if ratios else None,
                  "fastest": sum(probs[q][m]["max_cpu"] == min(probs[q][x]["max_cpu"] for x in models) for q in common),
                  "slow2": sum(r >= 2 for r in ratios), "cpu_total": sum(probs[q][m]["total_cpu"] for q in common),
                  "rss_median_mb": statistics.median(probs[q][m]["rss_kb"] for q in common) / 1024 if common else None,
                  "rss_max_mb": max(probs[q][m]["rss_kb"] for q in common) / 1024 if common else None}
    return {"measurable": measurable, "common": common, "models": agg}


def render_run(s, model, meta):
    probs = {q: d[model] for q, d in s["problems"].items() if model in d}
    L = [f"# 代码性能：{model}", "",
         f"- 通过的答案中测了 {len(probs)} 份；启动基线（空程序）CPU {1000 * s['baseline_cpu']:.1f} ms、峰值内存 "
         f"{s['baseline_rss_kb'] / 1024:.1f} MB，AtCoder 题的 CPU 已扣除基线"]
    bad = [q for m, q in s["failed"] if m == model]
    if bad:
        L.append(f"- 重跑时输出错误、出错或超时，不计入：{', '.join(bad)}")
    L += ["", LEGEND, "", "| 题目 | 难度 | 平台 | 测试数 | 最慢测试 CPU（秒）↓ | 全部测试 CPU（秒）↓ | 峰值内存（MB）↓ |",
          "|---|---|---|---:|---:|---:|---:|"]
    for q, v in sorted(probs.items(), key=lambda x: -x[1]["max_cpu"]):
        L.append(f"| {q} | {meta[q]['difficulty']} | {meta[q]['platform']} | {v['tests']} | {v['max_cpu']:.3f} | "
                 f"{v['total_cpu']:.3f} | {v['rss_kb'] / 1024:.0f} |")
    small = sum(v["max_cpu"] < THRESH for v in probs.values())
    L += ["", f"最慢测试不到 {THRESH} 秒的题有 {small} 道：耗时主要是进程启动，比较模型时不计入（见 cb perf 多个运行目录的对比）。"]
    return "\n".join(L) + "\n"


def render_compare(s, c, models, meta):
    probs = s["problems"]
    L = ["# 代码性能对比", "", f"- 运行：{', '.join(models)}",
         f"- 最慢答案的 CPU（扣除启动）≥ {THRESH} 秒的题 {len(c['measurable'])} 道，其中所有运行都通过的 {len(c['common'])} 道参与汇总",
         "", LEGEND, "",
         "| 运行 | 相对最快倍数（几何平均）↓ | 最快（题）↑ | 慢 ≥ 2 倍（题）↓ | CPU 合计（秒）↓ | 峰值内存中位数（MB）↓ | 峰值内存最大（MB）↓ |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for m in models:
        a = c["models"][m]
        f = lambda v, nd: "—" if v is None else f"{v:.{nd}f}"  # noqa: E731
        L.append(f"| {m} | {f(a['geo_mean'], 2)} | {a['fastest']} | {a['slow2']} | {a['cpu_total']:.1f} | "
                 f"{f(a['rss_median_mb'], 0)} | {f(a['rss_max_mb'], 0)} |")
    L += ["", "## 每题：最慢测试的 CPU 秒（括号内为相对最快者的倍数，≥ 2 时标出）", "", LEGEND, "",
          "| 题目 | 难度 | " + " | ".join(f"{m} ↓" for m in models) + " |", "|---|---|" + "---:|" * len(models)]
    for q in c["measurable"]:
        d = probs[q]
        best = min(v["max_cpu"] for v in d.values())
        cells = []
        for m in models:
            if m not in d:
                cells.append("—")
                continue
            v = d[m]["max_cpu"]
            cells.append(f"**{v:.2f}**" if v == best else f"{v:.2f}" + (f"（{v / best:.1f}×）" if best > 0 and v / best >= 2 else ""))
        L.append(f"| {q} | {meta[q]['difficulty']} | " + " | ".join(cells) + " |")
    L += ["", "粗体为该题最快。“最快”按严格最小值计；相差几个百分点在测量噪声之内。"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- measuring

def run_one(argv, stdin_path, stdout_path, launcher, basepy, timeout):
    p = subprocess.run([basepy, "-I", "-S", launcher, str(timeout), stdin_path, stdout_path, *argv],
                       capture_output=True, text=True)
    r = json.loads(p.stdout)
    return None if r["timeout"] else (r["cpu"], r["wall"], r["rss_kb"], r["status"])


def worker(job):
    core, qids, codes, tests, labels, reps, out_path, tmp, timeout = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lcb_rejudge import CHECK

    os.sched_setaffinity(0, {core})
    py, basepy = sys.executable, os.path.join(sys.base_prefix, "bin", "python3")
    launcher, lc = os.path.join(tmp, "launcher.py"), os.path.join(tmp, "lc_runner.py")
    empty, nul = os.path.join(tmp, f"empty_{core}.py"), os.path.join(tmp, f"nul_{core}.txt")
    open(empty, "w").write("pass\n")
    open(nul, "w").write("")
    lines = []
    for rep in range(20):  # startup baseline on this core
        cpu, wall, rss, _ = run_one([py, empty], nul, os.devnull, launcher, basepy, timeout)
        lines.append({"model": "baseline", "q": "-", "test": 0, "rep": rep, "core": core, "cpu": cpu, "wall": wall,
                      "rss_kb": rss, "ok": True})
    for q in qids:
        io = tests[q]
        fn = io.get("fn_name")
        for ti, (inp, exp) in enumerate(zip(io["inputs"], io["outputs"])):
            inp_path, out_ = os.path.join(tmp, f"in_{core}.txt"), os.path.join(tmp, f"out_{core}.txt")
            open(inp_path, "w").write(inp)
            for rep in range(reps):
                for m in labels[rep % len(labels):] + labels[:rep % len(labels)]:
                    if q not in codes[m]:
                        continue
                    rec = {"model": m, "q": q, "test": ti, "rep": rep, "core": core}
                    if fn:
                        r = run_one([py, lc, codes[m][q], fn, inp_path, out_], os.devnull, os.devnull, launcher, basepy,
                                    timeout)
                    else:
                        r = run_one([py, codes[m][q]], inp_path, out_, launcher, basepy, timeout)
                    if r is None:
                        rec.update(ok=False, kind="TLE")
                    else:
                        cpu, wall, rss, status = r
                        rec.update(cpu=cpu, wall=wall, rss_kb=rss)
                        try:
                            if status != 0:
                                rec.update(ok=False, kind="RE")
                            elif fn:
                                got = json.load(open(out_))
                                rec.update(ok=got["res"] == json.loads(exp), call_cpu=got["call_cpu"],
                                           call_wall=got["call_wall"])
                            else:
                                out = open(out_).read()
                                rec.update(ok=CHECK[q](inp, out, exp) if q in CHECK else out.split() == exp.split())
                        except (ValueError, KeyError, IndexError):
                            rec.update(ok=False, kind="WA")
                    lines.append(rec)
        fd = os.open(out_path, os.O_WRONLY | os.O_APPEND)  # one write per problem, so workers don't interleave
        os.write(fd, "".join(json.dumps(x) + "\n" for x in lines).encode())
        os.close(fd)
        lines = []
        print(f"  core {core}: {q} done", flush=True)
    return core


def load_run(run_dir):
    f = glob.glob(os.path.join(run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if len(f) != 1:
        raise SystemExit(f"expected one *_eval_all.json under {run_dir}/output, found {len(f)}")
    rows = json.load(open(f[0]))
    rj = os.path.join(run_dir, "rejudge.jsonl")
    verdict = {v["q"]: v["passed"] for v in map(json.loads, open(rj))} if os.path.exists(rj) else {}
    return [r for r in rows if verdict.get(r["question_id"], bool(r["graded_list"][0])) and r["code_list"][0].strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6, help="cores used (the highest-numbered ones this process may use)")
    ap.add_argument("--timeout", type=float, default=20, help="seconds per run")
    ap.add_argument("--out", help="also write the comparison of several runs here")
    a = ap.parse_args()
    dirs = [os.path.normpath(d) for d in a.run_dirs]
    names = [d.split(os.sep)[-2] for d in dirs]  # runs/<model>/<run>
    labels = names if len(set(names)) == len(names) else ["/".join(d.split(os.sep)[-2:]) for d in dirs]
    passing = {m: load_run(d) for m, d in zip(labels, dirs)}

    cb = os.environ["CB"]
    sys.path.insert(0, os.path.join(cb, "src", "LiveCodeBench"))
    import datasets
    _load = datasets.load_dataset
    local = os.path.join(cb, "data", "code_generation_lite")
    datasets.load_dataset = lambda path, *x, **k: _load(local if path == "livecodebench/code_generation_lite" else path, *x, **k)
    from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
    from lcb_runner.evaluation.testing_util import import_string

    want = {r["question_id"] for rs in passing.values() for r in rs}
    meta = {r["question_id"]: r for rs in passing.values() for r in rs}
    tests = {p.question_id: json.loads(p.get_evaluation_sample()["input_output"])
             for p in load_code_generation_dataset(os.environ.get("LCB_RELEASE", "release_v6")) if p.question_id in want}
    tmp = tempfile.mkdtemp(prefix="cbperf_")
    open(os.path.join(tmp, "lc_runner.py"), "w").write(LC_RUNNER.replace("__IMPORTS__", repr(import_string)))
    open(os.path.join(tmp, "launcher.py"), "w").write(LAUNCHER)
    codes = {}
    for m, rs in passing.items():
        for r in rs:
            path = os.path.join(tmp, f"{m.replace('/', '__')}__{r['question_id']}.py")
            open(path, "w").write(r["code_list"][0])
            codes.setdefault(m, {})[r["question_id"]] = path
    cores = sorted(os.sched_getaffinity(0))[-a.workers:]
    weight, buckets = [0] * len(cores), [[] for _ in cores]  # longest first, by total input size
    for q in sorted(want, key=lambda q: -sum(map(len, tests[q]["inputs"]))):
        i = weight.index(min(weight))
        buckets[i].append(q)
        weight[i] += sum(map(len, tests[q]["inputs"])) + 2000 * len(tests[q]["inputs"])
    raw = os.path.join(tmp, "perf.jsonl")
    open(raw, "w").close()
    print(f"measuring {sum(map(len, codes.values()))} answers on {len(want)} problems, {a.reps} reps, cores {cores}",
          flush=True)
    jobs = [(c, b, codes, tests, labels, a.reps, raw, tmp, a.timeout) for c, b in zip(cores, buckets)]
    with mp.Pool(len(cores)) as pool:
        for _ in pool.imap_unordered(worker, jobs):
            pass
    rows = [json.loads(l) for l in open(raw)]
    s = summarize(rows)
    for m, d in zip(labels, dirs):
        with open(os.path.join(d, "perf.jsonl"), "w") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows if r["model"] in (m, "baseline")))
        mine = {q: v[m] for q, v in s["problems"].items() if m in v}
        json.dump({"model": m, "baseline_cpu": s["baseline_cpu"], "baseline_rss_kb": s["baseline_rss_kb"],
                   "reps": a.reps, "problems": mine, "failed": [q for x, q in s["failed"] if x == m]},
                  open(os.path.join(d, "perf.json"), "w"), indent=1)
        open(os.path.join(d, "perf.md"), "w").write(render_run(s, m, meta))
        print(f"written {d}/perf.md")
    if len(labels) > 1:
        text = render_compare(s, compare(s, labels), labels, meta)
        if a.out:
            open(a.out, "w").write(text)
        print(text)
    else:
        print(render_run(s, labels[0], meta))


if __name__ == "__main__":
    main()
