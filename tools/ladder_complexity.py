"""Empirical time and space complexity of the solved answers of a ladder run, against the official solution.

  python ladder_complexity.py <run dir>       # writes <run dir>/complexity.jsonl

For every solved answer, on the official tests: x = input size in bytes, y = CPU time (or peak memory) minus what an
empty program of the same language needs. Over the tests where y is above the noise floor, the slope k of
log y = a + k log x is the empirical growth exponent (BigO(Bench)-style scaling, but on the official tests rather
than generated inputs). The official solution's exponent comes from the calibration run on the same tests, and the
answer is classed on the tests both measured, by the slope of log(answer / official) against log x:
  better  dk <= -DK   (grows more slowly than the official solution: a candidate for a better or novel algorithm)
  same    |dk| < DK
  worse   dk >= DK    (asymptotically worse, even if it passed the limits)
DK = 0.3 by default. A problem whose test inputs span less than 8x in size, or with fewer than 4 measurable tests,
is "not measurable" (the input size then says little about n, e.g. one number N up to 1e18).
"""
import argparse
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402

DK = float(os.environ.get("LADDER_DK", "0.3"))
MIN_CPU = 0.01      # s above the empty program
MIN_RSS_KB = 2048   # KB above the empty program
MIN_SPAN = 8.0      # largest / smallest input size among the fitted tests
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


def baseline(lang):
    """Median CPU and RSS of an empty program (5 runs)."""
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
        rs = [L.run(argv, os.path.join(work, "in"), os.path.join(work, "out"), work, 5, 256) for _ in range(5)]
        return statistics.median(r["cpu"] for r in rs), statistics.median(r["rss_kb"] for r in rs)
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def series(sizes, vals, base, floor):
    pts = [(sizes[n], v - base) for n, v in vals.items() if n in sizes and v - base >= floor and sizes[n] > 0]
    return dict((x, y) for x, y in pts)  # one point per input size (duplicate sizes keep the last)


def compare(sizes, ans, ref, base, floor):
    """ans/ref: test name -> value. Returns the fit of each and the relative slope on common tests."""
    out = {}
    for who, vals in (("answer", ans), ("ref", ref)):
        s = series(sizes, vals, base, floor) if vals else {}
        if len(s) >= MIN_POINTS and max(s) / min(s) >= MIN_SPAN:
            k, r2 = fit(list(s), list(s.values()))
            out[who] = {"k": round(k, 3), "r2": round(r2, 3), "n": len(s)}
    common = [n for n in ans if ref and n in ref and n in sizes and ans[n] - base >= floor and ref[n] - base >= floor]
    xs = [sizes[n] for n in common]
    if len(common) >= MIN_POINTS and xs and max(xs) / min(xs) >= MIN_SPAN:
        dk, r2 = fit(xs, [(ans[n] - base) / (ref[n] - base) for n in common])
        out["dk"] = round(dk, 3)
        out["class"] = "better" if dk <= -DK else "worse" if dk >= DK else "same"
        out["ratio_median"] = round(statistics.median((ans[n] - base) / (ref[n] - base) for n in common), 3)
    else:
        out["class"] = "not measurable"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    a = ap.parse_args()
    judged = {}
    for l in open(os.path.join(a.run_dir, "judge.jsonl")):
        r = json.loads(l)
        judged[r["q"]] = r
    bases = {}
    out = []
    for q, r in sorted(judged.items()):
        if not r["solved"]:
            continue
        meta = L.load_meta(r["pid"])
        lang = meta["lang"]
        if lang not in bases:
            bases[lang] = baseline(lang)
        b_cpu, b_rss = bases[lang]
        tdir = os.path.join(L.PROBLEMS, r["pid"], "tests")
        sizes = {t["name"]: os.path.getsize(os.path.join(tdir, t["in"])) for t in meta["tests"]}
        ref = (meta.get("ref") or {}).get(lang) or {}
        cpu = {t["name"]: t["cpu"] for t in r["tests"]}
        rss = {t["name"]: t.get("rss_kb", 0) for t in r["tests"]}
        rec = {"q": q, "pid": r["pid"], "tier": r["tier"], "subset": r.get("subset"), "lang": lang,
               "ref_file": ref.get("file"),
               "time": compare(sizes, cpu, ref.get("cpu"), b_cpu, MIN_CPU),
               "space": compare(sizes, rss, ref.get("rss"), b_rss, MIN_RSS_KB)}
        out.append(rec)
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
