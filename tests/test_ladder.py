"""Ladder pipeline on synthetic problems (no downloads): the native judge for every judge kind and time-limit rule,
then generation against tests/mock_openai.py, judging, performance re-runs and the report.

  python tests/test_ladder.py          # needs g++, and openai + httpx for the end-to-end part
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CB = tempfile.mkdtemp(prefix="cb_ladder_test_")
os.environ["CB"] = CB
os.environ["LADDER_CORES"] = "4"
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ladder_lib as L  # noqa: E402
import ladder_judge as J  # noqa: E402

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
SUM_CPP = "#include <cstdio>\nint main(){long long a,b;scanf(\"%lld %lld\",&a,&b);printf(\"%lld\\n\",a+b);}\n"
SLOW_PY = "import time\na, b = map(int, input().split())\nt = time.process_time()\nwhile time.process_time() - t < 0.3: pass\nprint(a + b)\n"
LOOP_CPP = "int main(){volatile long x=0; for(;;) x++;}\n"
HOG_CPP = ("#include <cstdio>\n#include <cstring>\n#include <cstdlib>\nint main(){long long a,b;scanf(\"%lld %lld\",&a,&b);"
           "char*p=(char*)malloc(200<<20); if(!p) return 1; memset(p,1,200<<20); printf(\"%lld\\n\",a+b+p[5]-1);}\n")
CMS_CHECKER = r'''#include <cstdio>
int main(int argc, char** argv) {  // checker <input> <correct> <contestant>: full point if equal, half if off by one
    long long c, x; FILE* a = fopen(argv[2], "r"); FILE* b = fopen(argv[3], "r");
    if (fscanf(a, "%lld", &c) != 1 || fscanf(b, "%lld", &x) != 1) { printf("0\n"); fprintf(stderr, "no number\n"); return 0; }
    printf(x == c ? "1\n" : (x == c + 1 || x == c - 1) ? "0.5\n" : "0\n"); fprintf(stderr, "checked\n"); return 0; }
'''
TESTLIB_CHECKER = r'''#include <cstdio>
int main(int argc, char** argv) {  // chk <input> <output> <answer>, testlib's exit codes: 0 ok, 1 wa, 7 points
    long long c, x; FILE* o = fopen(argv[2], "r"); FILE* a = fopen(argv[3], "r");
    if (fscanf(o, "%lld", &x) != 1 || fscanf(a, "%lld", &c) != 1) { puts("wrong output format"); return 2; }
    if (x == c) { puts("ok"); return 0; }
    if (x == c * 2) { puts("points Ratio: 0.25"); return 7; }
    puts("wrong answer"); return 1; }
'''
INTERACTOR = r'''#include <cstdio>
int main(int argc, char** argv) {  // interactor <in> <tout> <ans>: sends n, expects 2n back
    long long n; FILE* f = fopen(argv[1], "r"); fscanf(f, "%lld", &n);
    printf("%lld\n", n); fflush(stdout);
    long long r; if (scanf("%lld", &r) != 1) { fprintf(stderr, "no reply\n"); return 1; }
    if (r == 2 * n) { fprintf(stderr, "ok Ratio: 1\n"); return 0; }
    fprintf(stderr, "wrong Ratio: 0\n"); return 1; }
'''
DOUBLE_CPP = "#include <cstdio>\nint main(){long long n; scanf(\"%lld\",&n); printf(\"%lld\\n\",2*n); fflush(stdout);}\n"


def problem(pid, tier, lang, kind, tests, scoring=None, files=None, tl=1.0, ml=64, ref=None, extra=None):
    d = os.path.join(L.PROBLEMS, pid)
    os.makedirs(os.path.join(d, "tests"))
    os.makedirs(os.path.join(d, "checker"))
    os.makedirs(os.path.join(d, "ref"))
    meta_tests = []
    for i, (inp, out) in enumerate(tests):
        open(os.path.join(d, "tests", f"{i}.in"), "w").write(inp)
        open(os.path.join(d, "tests", f"{i}.out"), "w").write(out)
        meta_tests.append({"name": str(i), "in": f"{i}.in", "out": f"{i}.out"})
    for name, text in (files or {}).items():
        open(os.path.join(d, "checker", name), "w").write(text)
    cands = []
    if ref:
        f = "ref." + ("py" if lang == "python" else "cpp")
        open(os.path.join(d, "ref", f), "w").write(ref)
        cands.append({"file": f, "lang": lang})
    statement = f"Problem {pid}: read the input and print the answer. (synthetic test problem)"
    open(os.path.join(d, "statement.md"), "w").write(statement + "\n")
    meta = {"pid": pid, "source": "test", "subset": "test", "tier": tier, "lang": lang, "title": pid, "contest": "test",
            "date": "2026-01", "url": "", "tl": tl, "ml": ml, "judge": kind, "scoring": scoring or {"type": "tests"},
            "tests": meta_tests, "ref_candidates": cands}
    meta.update(extra or {})
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"))
    return meta


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def main():
    sums = [("1 2\n", "3\n"), ("10 20\n", "30\n"), ("-5 5\n", "0\n")]
    p1 = problem("t-sum-py", "L1", "python", {"kind": "tokens"}, sums, ref=SUM_PY)
    r = J.judge_code(p1, SUM_PY, "python", workers=3)
    check(r["solved"] and r["strict_solved"] and r["score"] == 100, "python tokens: right answer solves")
    r = J.judge_code(p1, "print(0)\n", "python", workers=3)
    check(not r["solved"] and abs(r["score"] - 100 / 3) < 0.01, "python tokens: one of three tests right -> 33.3")
    p1s = dict(p1, tl=0.1)
    r = J.judge_code(p1s, SLOW_PY, "python", workers=3)
    check(r["solved"] and not r["strict_solved"] and r["strict_score"] == 0, "0.3 s CPU, 0.1 s limit: lenient solved, official not")
    r = J.judge_code(p1, "syntax error here(\n", "python", workers=3)
    check(r["score"] == 0 and r["verdicts"].get("RE") == 3, "python syntax error -> RE")

    p2 = problem("t-sum-cpp", "L3", "cpp", {"kind": "tokens"}, sums, ref=SUM_CPP)
    r = J.judge_code(p2, SUM_CPP, "cpp", workers=3)
    check(r["solved"], "c++ tokens: right answer solves")
    r = J.judge_code(dict(p2, tl=0.2), LOOP_CPP, "cpp", workers=3)
    check(r["verdicts"].get("TLE") == 3, "endless loop -> TLE")
    r = J.judge_code(p2, "int main( {\n", "cpp", workers=3)
    check(r["verdicts"].get("CE") == 3 and r["compile_error"], "compile error -> CE")
    if sys.platform.startswith("linux"):
        r = J.judge_code(p2, HOG_CPP, "cpp", workers=3)
        check(not r["solved"] and set(r["verdicts"]) <= {"MLE", "RE", "WA"}, "200 MB with a 64 MB limit -> not solved")

    groups = {"type": "groupmin", "groups": [{"max_score": 30, "tests": ["0"]}, {"max_score": 70, "tests": ["1", "2"]}]}
    p3 = problem("t-cms", "L3", "cpp", {"kind": "checker", "convention": "cms", "source": "checker/checker.cpp"}, sums,
                 scoring=groups, files={"checker.cpp": CMS_CHECKER})
    off = SUM_CPP.replace("a+b", "a+b+(a==10)")  # off by one on test 1 -> 0.5 there
    r = J.judge_code(p3, off, "cpp", workers=3)
    check(abs(r["score"] - (30 + 70 * 0.5)) < 1e-6 and not r["solved"], "CMS checker + GroupMin: 30 + 70 x 0.5 = 65")

    p4 = problem("t-testlib", "L5", "cpp", {"kind": "testlib", "checker": "chk.cc", "interactor": None}, sums,
                 scoring={"type": "mean"}, files={"chk.cc": TESTLIB_CHECKER})
    dbl = SUM_CPP.replace("a+b", "2*(a+b)")
    r = J.judge_code(p4, dbl, "cpp", workers=3)
    check(abs(r["score"] - (25 + 25 + 100) / 3) < 1e-6, "testlib points: Ratio 0.25 on two tests, exact on 0+0 -> 50")
    p5 = problem("t-inter", "L5", "cpp", {"kind": "testlib", "checker": "chk.cc", "interactor": "interactor.cc"},
                 [("4\n", "8\n"), ("7\n", "14\n")], scoring={"type": "mean"}, files={"interactor.cc": INTERACTOR})
    r = J.judge_code(p5, DOUBLE_CPP, "cpp", workers=2)
    check(r["solved"] and r["score"] == 100, "interactive: right protocol solves")
    r = J.judge_code(p5, DOUBLE_CPP.replace("2*n", "3*n"), "cpp", workers=2)
    check(r["score"] == 0, "interactive: wrong replies score 0")

    import ladder_build as B
    for pid in ("t-sum-py", "t-sum-cpp"):
        B.calibrate(pid, workers=3)
        check("python" in L.load_meta(pid)["ref"] or "cpp" in L.load_meta(pid)["ref"], f"calibrate {pid}: reference kept")
    check(L.extract_code("x\n```python\nprint(1)\n```\ny\n```cpp\nint main(){}\n```", "python") == "print(1)\n",
          "extract_code picks the block of the language")

    try:
        import openai  # noqa: F401
    except ImportError:
        print("skip end-to-end part: openai not installed")
        return
    os.makedirs(os.path.join(CB, "samples"))
    json.dump({"version": "test", "tiers": {"L1": ["t-sum-py"], "L2": [], "L3": ["t-sum-cpp", "t-cms"], "L4": [],
                                             "L5": ["t-testlib"]}}, open(os.path.join(CB, "samples", "ladder.json"), "w"))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "mock_openai.py"), "--port", str(port)],
                            env=dict(os.environ), stdout=subprocess.PIPE, text=True)
    try:
        mock.stdout.readline()
        run = os.path.join(CB, "runs", "mock", "ladder-full")
        env = dict(os.environ, MODEL="mock", OPENAI_BASE_URL=f"http://127.0.0.1:{port}/v1", OPENAI_API_KEY="x",
                   WORKERS="4", LADDER_N="L1=2,L3=1,L5=1")
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "ladder_run.py"), "--out", run], env=env, check=True)
        answers = [json.loads(l) for l in open(os.path.join(run, "answers.jsonl"))]
        check(len(answers) == 5 and all(a["code"] for a in answers if a["pid"] in ("t-sum-py", "t-sum-cpp")),
              "ladder_run: 5 samples answered, code extracted")
        calls = [json.loads(l) for l in open(os.path.join(run, "usage.jsonl"))]
        check(all(c.get("first_token") and c.get("usage") for c in calls), "usage log: first-token time and usage per call")
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "ladder_run.py"), "--out", run], env=env, check=True)
        check(len([json.loads(l) for l in open(os.path.join(run, "usage.jsonl"))]) == len(calls), "re-run asks nothing again")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "ladder_judge.py"), run, "--workers", "4",
                        "--perf-reps", "1", "--min-ref-cpu", "0"], env=env, check=True)
        judged = {json.loads(l)["q"]: json.loads(l) for l in open(os.path.join(run, "judge.jsonl"))}
        check(judged["t-sum-py#0"]["solved"] and judged["t-sum-cpp#0"]["solved"], "judge: reference answers solve")
        check(os.path.exists(os.path.join(run, "perf.jsonl")), "perf re-runs written")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "ladder_report.py"), run, "--out",
                        os.path.join(run, "report")], env=env, check=True)
        rep = json.load(open(os.path.join(run, "report", "report.json")))[0]
        check(rep["tiers"]["L1"]["pass1"] == 100 and rep["tiers"]["L1"]["samples"] == 2, "report: L1 pass@1 100 over 2 samples")
        check(os.path.exists(os.path.join(run, "report", "main.tex")), "report: LaTeX written")
    finally:
        mock.terminate()
    shutil.rmtree(CB, ignore_errors=True)
    print("all ladder tests passed")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"{time.time() - t0:.1f} s")
