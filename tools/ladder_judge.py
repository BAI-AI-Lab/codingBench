"""Judge the answers of a ladder run (bin/ladder_run.py) on the official tests, natively.

  python ladder_judge.py <run dir> [--workers 64] [--perf-reps 3]

Writes <run dir>/judge.jsonl, one line per answer: per test the verdict (ok/WA/TLE/MLE/RE/CE), score in [0, 1], CPU
time, wall time and peak memory; per answer the problem score (source's rule, 0-100) and "solved" (every test
right), each under the lenient limit (LADDER_LENIENT x official: is the algorithm right?) and under the official
limit (is it also fast enough?). With --perf-reps, solved answers of problems that have a reference solution are
re-run on their 3 heaviest tests (by the reference's CPU time) interleaved with the reference, --perf-reps times
each, and the medians go to perf.jsonl (ratio = answer / reference CPU on the slowest of those tests).
"""
import argparse
import concurrent.futures
import json
import os
import queue
import shutil
import statistics
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402

_cores = None
_lock = threading.Lock()


def cpu_quota():
    """CPUs a container's cgroup actually allows (cgroup v2 cpu.max or v1 cfs quota), rounded up; None = no quota.
    nproc and the affinity mask show the host's cores, e.g. 96 on a box that may use half of one."""
    import math
    try:
        q, p = open("/sys/fs/cgroup/cpu.max").read().split()[:2]
        if q != "max":
            return max(1, math.ceil(int(q) / int(p)))
    except (OSError, ValueError):
        pass
    try:
        q = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
        p = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        if q > 0:
            return max(1, math.ceil(q / p))
    except (OSError, ValueError):
        pass
    return None


def cores(n):
    """A pool of the n highest cores of this process's affinity mask (each test run holds one), or None slots; never
    more than the cgroup CPU quota, so runs do not share a core and stretch past their wall-clock limit."""
    global _cores
    with _lock:
        if _cores is None:
            avail = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
            q = cpu_quota()
            if q:
                n = min(n, q)
            _cores = queue.Queue()
            for c in (avail[-n:] if avail else [None] * n):
                _cores.put(c)
    return _cores


def _compile_once(meta, what, sources, out, flags=None):
    """Compile a checker / interactor / manager into problems/<pid>/checker/bin/ once (shared by all answers)."""
    d = os.path.join(L.PROBLEMS, meta["pid"], "checker")
    binp = os.path.join(d, "bin", out)
    with _lock:
        if os.path.exists(binp):
            return binp, ""
        os.makedirs(os.path.dirname(binp), exist_ok=True)
        ok, log = L.compile_cpp([os.path.join(d, s) for s in sources], binp + ".tmp", includes=[d], flags=flags)
        if not ok:
            return None, log
        os.replace(binp + ".tmp", binp)
    return binp, ""


def build(meta, code, lang, work):
    """Answer -> (argv, None) or (None, compile error)."""
    j = meta["judge"]
    if lang == "python":
        open(os.path.join(work, "sol.py"), "w").write(code)
        return [L.PYTHON, "-I", "-S", "-B", "sol.py"], None
    cdir = os.path.join(L.PROBLEMS, meta["pid"], "checker")
    src = os.path.join(work, meta.get("filename") or "sol.cpp")
    open(src, "w").write(code)
    sources, includes, flags = [src], [], None
    if j["kind"] in ("grader", "communication"):
        sources.append(os.path.join(cdir, j["grader"]))
        includes.append(cdir)
        flags = ["-DEVAL", "-O2", "-pipe", "-std=gnu++20"]  # IOI 2026's CMS command, minus -static -s
    ok, log = L.compile_cpp(sources, os.path.join(work, "sol"), includes=includes, flags=flags)
    return ([os.path.join(work, "sol")], None) if ok else (None, log)


def judge_test(meta, t, argv, work, lenient=None):
    """Run one test; returns the per-test record."""
    pdir = os.path.join(L.PROBLEMS, meta["pid"])
    tl = t.get("tl") or meta["tl"]
    ml = t.get("ml") or meta["ml"]
    run_tl = tl * (lenient or L.LENIENT)
    inp = os.path.join(pdir, "tests", t["in"])
    ans = os.path.join(pdir, "tests", t["out"]) if t.get("out") else None
    out = os.path.join(work, f"{t['name']}.txt")
    err = os.path.join(work, f"{t['name']}.err")
    j = meta["judge"]
    pool = cores(int(os.environ.get("LADDER_CORES", "64")))
    core = pool.get()
    try:
        if j["kind"] == "testlib" and j.get("interactor"):
            ib, log = _compile_once(meta, "interactor", [j["interactor"]], "interactor")
            if not ib:
                return {"name": t["name"], "verdict": "JE", "score": 0.0, "cpu": 0.0, "msg": log[-300:]}
            # file names per test: the tests of one answer run in parallel in the same work dir
            tin, tout, tans = (f"{t['name']}.{x}.txt" for x in ("in", "tout", "ans"))
            shutil.copy(inp, os.path.join(work, tin))
            shutil.copy(ans, os.path.join(work, tans))
            r = L.run(argv, None, None, work, run_tl, ml, core=core, stderr=err, interactor=[ib, tin, tout, tans])
            msg = open(err, errors="replace").read()[-2000:] if os.path.exists(err) else ""
            score = L.interactor_score(r.get("int_status", 0), msg) if r["verdict"] == "ok" else 0.0
            rec = {"verdict": r["verdict"] if r["verdict"] != "ok" else
                   ("ok" if score >= 1 - 1e-9 else ("partial" if score > 0 else "WA")), "score": score}  # as for checkers
        else:
            r = L.run(argv, inp, out, work, run_tl, ml, core=core)
            if r["verdict"] != "ok":
                rec = {"verdict": r["verdict"], "score": 0.0}
            elif j["kind"] == "tokens" or (j["kind"] == "grader" and not j.get("checker")):
                ok = L.tokens_equal(out, ans)
                rec = {"verdict": "ok" if ok else "WA", "score": 1.0 if ok else 0.0}
            else:
                conv = "testlib" if j["kind"] == "testlib" else "cms"
                src = [j["checker"]] if j["kind"] == "testlib" else [os.path.basename(j.get("source") or j.get("checker"))]
                cb, log = _compile_once(meta, "checker", src, "checker")
                if not cb:
                    return {"name": t["name"], "verdict": "JE", "score": 0.0, "cpu": r["cpu"], "msg": log[-300:]}
                score, msg = L.run_checker(conv, cb, inp, out, ans or os.devnull, work)
                rec = {"verdict": "ok" if score >= 1 - 1e-9 else ("partial" if score > 0 else "WA"), "score": score,
                       "msg": msg[:200]}
    finally:
        pool.put(core)
    rec.update(name=t["name"], cpu=round(r["cpu"], 4), wall=round(r.get("wall", 0), 4), rss_kb=r.get("rss_kb", 0),
               tl=tl, strict_ok=rec["score"] > 0 and r["cpu"] <= tl)
    for f in (out, err):
        if os.path.exists(f):
            os.remove(f)
    return rec


def judge_code(meta, code, lang, workers=8, lenient=None):
    """Judge one program on every test of a problem."""
    work = L.tmpdir(f"ladder_{meta['pid']}_")
    try:
        argv, cerr = build(meta, code, lang, work)
        if argv is None:
            tests = [{"name": t["name"], "verdict": "CE", "score": 0.0, "cpu": 0.0, "rss_kb": 0, "strict_ok": False}
                     for t in meta["tests"]]
        else:
            with concurrent.futures.ThreadPoolExecutor(max(1, workers)) as ex:
                tests = list(ex.map(lambda t: judge_test(meta, t, argv, work, lenient), meta["tests"]))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    scores = {t["name"]: t["score"] for t in tests}
    strict = {t["name"]: (t["score"] if t.get("strict_ok") else 0.0) for t in tests}
    ok = [t for t in tests if t["score"] > 0]
    return {"pid": meta["pid"], "score": round(L.problem_score(meta, scores), 3), "solved": L.solved(meta, scores),
            "strict_score": round(L.problem_score(meta, strict), 3), "strict_solved": L.solved(meta, strict),
            "max_cpu": max((t["cpu"] for t in ok), default=0.0), "total_cpu": round(sum(t["cpu"] for t in ok), 4),
            "max_rss_kb": max((t.get("rss_kb", 0) for t in ok), default=0),
            "compile_error": (cerr or "")[-1500:] or None,
            "verdicts": {v: sum(t["verdict"] == v for t in tests) for v in sorted({t["verdict"] for t in tests})},
            "tests": tests}


# ---------------------------------------------------------------- performance re-runs

def perf(meta, code, lang, reps=3, heavy=3):
    """Median CPU of the answer and of the reference on the reference's `heavy` slowest tests, interleaved."""
    ref = (meta.get("ref") or {}).get(lang)
    if not ref:
        return None
    names = sorted(ref["cpu"], key=lambda n: -ref["cpu"][n])[:heavy]
    tests = [t for t in meta["tests"] if t["name"] in names]
    pdir = os.path.join(L.PROBLEMS, meta["pid"])
    ref_code = open(os.path.join(pdir, "ref", ref["file"])).read()
    w_a, w_r = L.tmpdir("perf_a_"), L.tmpdir("perf_r_")
    try:
        a, ea = build(meta, code, lang, w_a)
        b, eb = build(meta, ref_code, lang, w_r)
        if a is None or b is None:
            return None
        cpu = {"answer": {}, "ref": {}}
        for i in range(reps):
            order = [("answer", a, w_a), ("ref", b, w_r)] if i % 2 == 0 else [("ref", b, w_r), ("answer", a, w_a)]
            for t in tests:
                for who, argv, w in order:
                    r = judge_test(meta, t, argv, w)
                    if r["score"] <= 0:
                        return None
                    cpu[who].setdefault(t["name"], []).append(r["cpu"])
    finally:
        shutil.rmtree(w_a, ignore_errors=True)
        shutil.rmtree(w_r, ignore_errors=True)
    med = {who: {n: statistics.median(v) for n, v in d.items()} for who, d in cpu.items()}
    slow = max(names, key=lambda n: med["ref"].get(n, 0))
    return {"tests": names, "answer_cpu": med["answer"], "ref_cpu": med["ref"], "ref_file": ref["file"],
            "ratio": med["answer"][slow] / max(1e-3, med["ref"][slow]),
            "ratio_total": sum(med["answer"].values()) / max(1e-3, sum(med["ref"].values()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("LADDER_CORES", "64")))
    ap.add_argument("--perf-reps", type=int, default=3)
    ap.add_argument("--min-ref-cpu", type=float, default=0.05,
                    help="re-run for performance only when the reference needs at least this much CPU on a test")
    a = ap.parse_args()
    os.environ["LADDER_CORES"] = str(a.workers)
    answers = [json.loads(l) for l in open(os.path.join(a.run_dir, "answers.jsonl")) if l.strip()]
    last = {}
    for r in answers:  # the last answer per (problem, sample) counts
        last[r["q"]] = r
    out = os.path.join(a.run_dir, "judge.jsonl")
    done = {}
    if os.path.exists(out):
        for l in open(out):
            r = json.loads(l)
            done[(r["q"], r.get("code_hash"))] = r
    todo = [r for r in last.values() if (r["q"], r.get("code_hash")) not in done]
    # answers to problems found not judgeable after the run started (interactive / communication tasks, which
    # the problem list now leaves out): skipped
    skip = [r for r in todo if L.load_meta(r["pid"])["judge"]["kind"] == "communication"]
    todo = [r for r in todo if r not in skip]
    print(f"{len(last)} answers, {len(todo)} to judge"
          + (f", {len(skip)} to communication tasks skipped (not supported)" if skip else ""))
    per_answer = max(1, a.workers // 8)

    def one(r):
        try:
            return judge_one(r)
        except Exception as e:  # one broken problem does not stop the rest; it stays unjudged and is retried next time
            print(f"{r['q']}: judge error {e!r}", flush=True)
            return None

    def judge_one(r):
        meta = L.load_meta(r["pid"])
        if not r.get("code"):
            res = {"pid": r["pid"], "score": 0.0, "solved": False, "strict_score": 0.0, "strict_solved": False,
                   "max_cpu": 0.0, "total_cpu": 0.0, "max_rss_kb": 0, "compile_error": None,
                   "verdicts": {"no code": len(meta["tests"])}, "tests": []}
        else:
            res = judge_code(meta, r["code"], meta["lang"], workers=per_answer)
        res.update(q=r["q"], k=r.get("k", 0), tier=meta["tier"], source=meta["source"], subset=meta["subset"],
                   code_hash=r.get("code_hash"))
        return res

    with open(out, "a") as f, concurrent.futures.ThreadPoolExecutor(8) as ex:
        for res in ex.map(one, todo):
            if res is None:
                continue
            f.write(json.dumps(res) + "\n")
            f.flush()
            print(f"{res['q']:<28} {res['tier']} score {res['score']:6.1f} strict {res['strict_score']:6.1f} "
                  f"{'SOLVED' if res['solved'] else ''} {res['verdicts']}")
    if a.perf_reps <= 0:
        return
    judged = {}
    for l in open(out):
        r = json.loads(l)
        judged[r["q"]] = r
    pout = os.path.join(a.run_dir, "perf.jsonl")
    pdone = {json.loads(l)["q"] for l in open(pout)} if os.path.exists(pout) else set()
    with open(pout, "a") as f:
        for q, r in judged.items():
            if q in pdone or not r["solved"]:
                continue
            meta = L.load_meta(r["pid"])
            ref = (meta.get("ref") or {}).get(meta["lang"])
            if not ref or max(ref["cpu"].values(), default=0) < a.min_ref_cpu:
                continue
            p = perf(meta, last[q]["code"], meta["lang"], reps=a.perf_reps)
            if p:
                p.update(q=q, pid=r["pid"], tier=r["tier"])
                f.write(json.dumps(p) + "\n")
                f.flush()
                print(f"perf {q:<28} x{p['ratio']:.2f} of the reference")


if __name__ == "__main__":
    main()
