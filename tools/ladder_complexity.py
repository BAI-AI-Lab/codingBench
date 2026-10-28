"""Empirical time and space complexity of the solved answers of a ladder run, against the official solution.

  python ladder_complexity.py <run dir> [--reps 5] [--max-tests 20] [--workers 96]   # writes complexity.jsonl

Official tests are not a scaling series: in USACO most of the tests that take measurable time are all at the maximum
size, so the input size barely varies among them. The growth is therefore measured against the official solution's
own work: on every test where the official solution needs at least 2 ms of CPU beyond an empty program (up to
--max-tests of them, spread over that range), the answer and the official solution run --reps times each,
interleaved on pinned cores, and the medians count. With x = official CPU and y = answer CPU (startup subtracted),
the slope k of log y = a + k log x says how the answer's cost grows with the official solution's: if the official
solution is Theta(f(n)) and the answer is Theta(f(n)^k), k is that exponent.
  better      k <= 0.75, R^2 >= 0.8, and on the official solution's 3 heaviest tests the answer is at least 2x faster
              (grows more slowly than the official solution: a candidate for a better or novel algorithm, listed
              for manual review)
  same        0.75 < k < 1.33 and R^2 >= 0.8
  worse       k >= 1.33, R^2 >= 0.8, and at least 2x slower on those tests (asymptotically worse, even if it passed)
  uncertain   R^2 < 0.8, or a slope the heaviest tests contradict: a fixed cost in one program (e.g. setting up
              large arrays) bends the log-log line, so a low or high k alone is not trusted
  not measurable  fewer than 4 such tests, or their official CPU times span less than 4x
Space is classed the same way with peak memory (at least 1 MB above an empty program). Where the input sizes of those
tests do span at least 8x, the input-size exponents of both programs are reported too (k_size).
"""
import argparse
import concurrent.futures
import json
import math
import os
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402

BETTER, WORSE, MIN_R2 = 0.75, 1.33, 0.8
TOP_TESTS, TOP_FACTOR = 3, 2.0  # a better / worse verdict needs this factor on the official solution's heaviest tests
MIN_CPU = 0.002      # s above the empty program
MIN_RSS_KB = 1024    # KB above the empty program
MIN_SPAN = 4.0       # largest / smallest official value among the fitted tests
SIZE_SPAN = 8.0      # input sizes must span this much for the size exponent
MIN_POINTS = 4


def fit(xs, ys):
    """Least squares slope and R^2 of log y on log x."""
    lx, ly = [math.log(x) for x in xs], [math.log(y) for y in ys]
    mx, my = statistics.mean(lx), statistics.mean(ly)
    sxx = sum((a - mx) ** 2 for a in lx)
    if sxx == 0:
        return None, None
    k = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / sxx
    ss = sum((b - my) ** 2 for b in ly)
    res = sum((b - (my + k * (a - mx))) ** 2 for a, b in zip(lx, ly))
    return k, (1 - res / ss) if ss > 0 else 1.0


def classify(k, r2, top_ratio):
    if r2 is None or r2 < MIN_R2:
        return "uncertain"
    if k <= BETTER:
        return "better" if top_ratio <= 1 / TOP_FACTOR else "uncertain"
    if k >= WORSE:
        return "worse" if top_ratio >= TOP_FACTOR else "uncertain"
    return "same"


def relative(xs, ys, base, floor, sizes=None):
    """Points (official, answer) above the floor -> {k, r2, n, class, ratio_median[, k_size_answer, k_size_ref]}."""
    pts = [(x - base, y - base, s) for x, y, s in zip(xs, ys, sizes or [None] * len(xs))
           if x - base >= floor and y - base >= floor]
    if len(pts) < MIN_POINTS or max(p[0] for p in pts) / min(p[0] for p in pts) < MIN_SPAN:
        return {"class": "not measurable", "n": len(pts)}
    k, r2 = fit([p[0] for p in pts], [p[1] for p in pts])
    top = sorted(pts, key=lambda p: p[0])[-TOP_TESTS:]
    top_ratio = statistics.median(p[1] / p[0] for p in top)
    out = {"k": round(k, 3), "r2": round(r2, 3), "n": len(pts), "class": classify(k, r2, top_ratio),
           "ratio_median": round(statistics.median(p[1] / p[0] for p in pts), 3), "top_ratio": round(top_ratio, 3)}
    if sizes and all(p[2] for p in pts) and max(p[2] for p in pts) / min(p[2] for p in pts) >= SIZE_SPAN:
        out["k_size_answer"] = round(fit([p[2] for p in pts], [p[1] for p in pts])[0], 3)
        out["k_size_ref"] = round(fit([p[2] for p in pts], [p[0] for p in pts])[0], 3)
    return out


def baseline(lang):
    """Median CPU and RSS of an empty program (7 runs)."""
    work = L.tmpdir("cplx_base_")
    try:
        if lang == "python":
            open(os.path.join(work, "e.py"), "w").write("pass\n")
            argv = [L.PYTHON, "-I", "-S", "-B", "e.py"]
        else:
            open(os.path.join(work, "e.cpp"), "w").write("int main(){}\n")
            L.compile_cpp([os.path.join(work, "e.cpp")], os.path.join(work, "e"))
            argv = [os.path.join(work, "e")]
        open(os.path.join(work, "in"), "w").write("")
        rs = [L.run(argv, os.path.join(work, "in"), os.path.join(work, "out"), work, 5, 256) for _ in range(7)]
        return statistics.median(r["cpu"] for r in rs), statistics.median(r["rss_kb"] for r in rs)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def pick_tests(ref, base_cpu, max_tests):
    """Tests where the official solution needs >= MIN_CPU, spread evenly over its CPU range."""
    names = sorted((n for n, c in ref["cpu"].items() if c - base_cpu >= MIN_CPU), key=lambda n: ref["cpu"][n])
    if len(names) <= max_tests:
        return names
    step = (len(names) - 1) / (max_tests - 1)
    return sorted({names[round(i * step)] for i in range(max_tests)}, key=lambda n: ref["cpu"][n])


def measure(meta, code, ref_code, lang, names, reps):
    """Median CPU and peak memory per test for the answer and the official solution, runs interleaved."""
    import ladder_judge as J
    tests = [t for t in meta["tests"] if t["name"] in names]
    w_a, w_r = L.tmpdir("cplx_a_"), L.tmpdir("cplx_r_")
    try:
        a, _ = J.build(meta, code, lang, w_a)
        b, _ = J.build(meta, ref_code, lang, w_r)
        if a is None or b is None:
            return None
        runs = {"answer": {}, "ref": {}}
        for i in range(reps):
            order = [("answer", a, w_a), ("ref", b, w_r)] if i % 2 == 0 else [("ref", b, w_r), ("answer", a, w_a)]
            for t in tests:
                for who, argv, w in order:
                    r = J.judge_test(meta, t, argv, w)
                    if r["score"] > 0:
                        runs[who].setdefault(t["name"], []).append((r["cpu"], r.get("rss_kb", 0)))
    finally:
        shutil.rmtree(w_a, ignore_errors=True)
        shutil.rmtree(w_r, ignore_errors=True)
    ok = [t["name"] for t in tests if len(runs["answer"].get(t["name"], [])) == reps and len(runs["ref"].get(t["name"], [])) == reps]
    med = lambda who, n, j: statistics.median(x[j] for x in runs[who][n])  # noqa: E731
    return {n: {"a_cpu": med("answer", n, 0), "r_cpu": med("ref", n, 0), "a_rss": med("answer", n, 1),
                "r_rss": med("ref", n, 1)} for n in ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--max-tests", type=int, default=20)
    ap.add_argument("--workers", type=int, default=int(os.environ.get("LADDER_CORES", "64")))
    ap.add_argument("--reuse", action="store_true", help="re-class from the medians already in complexity.jsonl")
    a = ap.parse_args()
    os.environ["LADDER_CORES"] = str(a.workers)
    judged, answers = {}, {}
    for l in open(os.path.join(a.run_dir, "judge.jsonl")):
        r = json.loads(l)
        judged[r["q"]] = r
    for l in open(os.path.join(a.run_dir, "answers.jsonl")):
        r = json.loads(l)
        answers[r["q"]] = r
    bases = {lang: baseline(lang) for lang in ("python", "cpp")}
    old = {}
    if a.reuse and os.path.exists(os.path.join(a.run_dir, "complexity.jsonl")):
        old = {r["q"]: r for r in map(json.loads, open(os.path.join(a.run_dir, "complexity.jsonl")))}

    def one(q):
        r = judged[q]
        meta = L.load_meta(r["pid"])
        lang = meta["lang"]
        rec = {"q": q, "pid": r["pid"], "tier": r["tier"], "subset": r.get("subset"), "lang": lang}
        ref = (meta.get("ref") or {}).get(lang)
        if not ref:
            rec["time"] = rec["space"] = {"class": "no reference"}
            return rec
        b_cpu, b_rss = bases[lang]
        names = pick_tests(ref, b_cpu, a.max_tests)
        if len(names) < MIN_POINTS:
            rec["time"] = {"class": "not measurable", "n": len(names)}
            rec["space"] = {"class": "not measurable", "n": len(names)}
            return rec
        if q in old and old[q].get("tests"):
            m = old[q]["tests"]
        else:
            code = answers[q]["code"]
            ref_code = open(os.path.join(L.PROBLEMS, r["pid"], "ref", ref["file"])).read()
            m = measure(meta, code, ref_code, lang, names, a.reps)
        if not m:
            rec["time"] = rec["space"] = {"class": "not measurable", "n": 0}
            return rec
        ns = sorted(m, key=lambda n: m[n]["r_cpu"])
        tdir = os.path.join(L.PROBLEMS, r["pid"], "tests")
        sizes = [os.path.getsize(os.path.join(tdir, next(t["in"] for t in meta["tests"] if t["name"] == n))) for n in ns]
        rec["time"] = relative([m[n]["r_cpu"] for n in ns], [m[n]["a_cpu"] for n in ns], b_cpu, MIN_CPU, sizes)
        rec["space"] = relative([m[n]["r_rss"] for n in ns], [m[n]["a_rss"] for n in ns], b_rss, MIN_RSS_KB, sizes)
        rec["tests"] = {n: m[n] for n in ns}
        rec["ref_file"] = ref["file"]
        return rec

    todo = sorted(q for q, r in judged.items() if r["solved"] and q in answers)
    with concurrent.futures.ThreadPoolExecutor(max(1, a.workers // 4)) as ex:
        out = list(ex.map(one, todo))
    with open(os.path.join(a.run_dir, "complexity.jsonl"), "w") as f:
        for rec in out:
            f.write(json.dumps(rec) + "\n")
    for kind in ("time", "space"):
        c = {}
        for rec in out:
            c[rec[kind]["class"]] = c.get(rec[kind]["class"], 0) + 1
        print(f"complexity ({kind}): {c}")
    print(f"-> {a.run_dir}/complexity.jsonl")


if __name__ == "__main__":
    main()
