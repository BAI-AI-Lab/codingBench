"""Shared pieces of the ladder test set (cb ladder): paths, the problem files, prompts, and the native judge.

A problem lives in $CB/data/ladder/problems/<pid>/ (written by ladder_build.py):
  meta.json      tier, source, title, contest date, language, time/memory limits, judge kind, scoring, tests
  statement.md   the text the model gets (never committed or published)
  tests/         <name>.in and <name>.out (or .ans)
  checker/       compiled checker / interactor / grader files, when the problem needs them
  ref/           official solutions that passed every test (ladder_build.py --calibrate), with their timings

Judging is native (no Docker): every program runs as the unprivileged user that runs cb, through a small
`python -I -S` launcher that sets rlimits (address space, stack, CPU, output size), pins one core and reads the
child's rusage from wait4, so CPU time and peak memory are the program's own. Each test is judged once with a
lenient time limit (LENIENT x the official one); the verdict under the official limit follows from the CPU time,
so one run gives both the "algorithm is right" and the "fast enough" verdicts.
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

CB = os.environ.get("CB", "/data/hx/code_bench")
DATA = os.path.join(CB, "data", "ladder")
RAW = os.path.join(DATA, "raw")
PROBLEMS = os.path.join(DATA, "problems")
TIERS = ("L1", "L2", "L3", "L4", "L5")
LANG = {"L1": "python", "L2": "python", "L3": "cpp", "L4": "cpp", "L5": "cpp"}
LENIENT = float(os.environ.get("LADDER_LENIENT", "5"))   # lenient time limit = LENIENT x official
CXX = os.environ.get("CXX", "g++")
CXXFLAGS = ["-O2", "-pipe", "-std=gnu++17"]
PYTHON = os.environ.get("LADDER_PYTHON", sys.executable)  # the judge's Python for answers (standard library only)
OUT_LIMIT = 256 << 20  # bytes a program may write to stdout


def load_meta(pid):
    return json.load(open(os.path.join(PROBLEMS, pid, "meta.json")))


def load_manifest(path):
    """samples/ladder.json -> list of problem metas in manifest order (tier, then source, then id)."""
    m = json.load(open(path))
    return [load_meta(p) for t in TIERS for p in m["tiers"].get(t, [])]


# ---------------------------------------------------------------- prompts

PY_SYSTEM = ("You are an expert Python programmer. You will be given a question (problem specification) and will "
             "generate a correct Python program that matches the specification and passes all tests.")
CPP_SYSTEM = ("You are an expert competitive programmer. You will be given a question (problem specification) and "
              "will generate a correct and efficient C++17 program that matches the specification and passes all "
              "tests.")
FCS_SYSTEM = ("You are a competitive programmer. You will be given a problem statement, please implement a solution "
              "in C++. The execution time and memory limit are also stated in the statement so be aware of the "
              "complexity of the program. Please wrap the code in ```cpp and ``` so that it is properly formatted. "
              "Your response should ONLY contain the C++ code, with no additional explanation or text.")


def limits_line(meta):
    return (f"Time limit: {meta['tl']:g} seconds per test. Memory limit: {meta['ml']} MB. "
            + ("Python 3 standard library only." if meta["lang"] == "python"
               else "Compiled with g++ -O2 -std=gnu++17."))


def prompt(meta, statement):
    """(system, user) messages for a problem. stdin/stdout problems follow LiveCodeBench's wording; grader problems
    (IOI) ask for the functions only; FrontierCS uses its own published prompt, so scores stay comparable."""
    if meta["source"] == "frontiercs":
        return None, f"{FCS_SYSTEM}\n\nProblem:\n\n{statement}\n\nGenerate solution code:"
    if meta["lang"] == "python":
        fmt = ("Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on "
               "the sample inputs). Enclose your code within delimiters as follows. Ensure that when the python "
               "program runs, it reads the inputs, runs the algorithm and writes output to STDOUT.\n"
               "```python\n# YOUR CODE HERE\n```")
        system = PY_SYSTEM
    elif meta["judge"]["kind"] == "grader":
        fmt = ("Implement the procedures described above in a single C++17 file. Do not write a main function and do "
               "not read from stdin or write to stdout: the official grader calls your procedures. Include the "
               f"header with #include \"{meta['judge']['header']}\". Enclose your code within delimiters as follows.\n"
               "```cpp\n// YOUR CODE HERE\n```")
        system = CPP_SYSTEM
    else:
        fmt = ("Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on "
               "the sample inputs). Enclose your code within delimiters as follows. Ensure that when the C++ program "
               "runs, it reads the inputs, runs the algorithm and writes output to STDOUT.\n```cpp\n// YOUR CODE HERE\n```")
        system = CPP_SYSTEM
    user = f"### Question:\n{statement}\n\n{limits_line(meta)}\n\n### Format: {fmt}\n\n### Answer: (use the provided format with backticks)\n\n"
    return system, user


def extract_code(text, lang):
    """The last fenced code block of the wanted language in an answer (LiveCodeBench's rule), else the last block."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    blocks = re.findall(r"```([A-Za-z0-9+#]*)[^\n]*\n(.*?)```", text, re.S)
    if not blocks:
        return ""
    want = {"python": ("python", "py", "python3"), "cpp": ("cpp", "c++", "cc", "cxx")}[lang]
    hit = [b for tag, b in blocks if tag.lower() in want]
    return (hit or [b for _, b in blocks])[-1].strip() + "\n"


# ---------------------------------------------------------------- running programs

LAUNCHER = r'''
import json, os, resource, signal, sys, time
cfg = json.loads(sys.argv[1])
def limits():
    if cfg.get("core") is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {cfg["core"]})
    for name, val in (("RLIMIT_AS", cfg.get("as")), ("RLIMIT_STACK", cfg.get("stack")), ("RLIMIT_CPU", cfg.get("cpu")),
                      ("RLIMIT_FSIZE", cfg.get("fsize")), ("RLIMIT_CORE", 0)):
        if val is not None and hasattr(resource, name):
            r = getattr(resource, name)
            hard = resource.getrlimit(r)[1]
            v = val if hard == resource.RLIM_INFINITY else min(val, hard)
            try:
                resource.setrlimit(r, (v, v if hard == resource.RLIM_INFINITY else hard))
            except (ValueError, OSError):
                pass
def child(argv, fin, fout, ferr, cwd):
    os.chdir(cwd)
    for fd, target in ((0, fin), (1, fout), (2, ferr)):
        if target != fd:
            os.dup2(target, fd)
    limits()
    os.execv(argv[0], argv)
t0 = time.perf_counter()
timed_out = []
pids = []
def kill(*_):
    timed_out.append(1)
    for p in pids:
        try:
            os.kill(p, 9)
        except ProcessLookupError:
            pass
signal.signal(signal.SIGALRM, kill)
null = os.open(os.devnull, os.O_WRONLY)
if cfg.get("interactor"):
    # solution <-> interactor through two pipes; the interactor reads the test input from a file
    a_r, a_w = os.pipe()  # solution -> interactor
    b_r, b_w = os.pipe()  # interactor -> solution
    err = os.open(cfg["stderr"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC) if cfg.get("stderr") else null
    p_sol = os.fork()
    if p_sol == 0:
        for fd in (a_r, b_w):
            os.close(fd)
        child(cfg["argv"], b_r, a_w, null, cfg["cwd"])
    p_int = os.fork()
    if p_int == 0:
        for fd in (a_w, b_r):
            os.close(fd)
        cfg_core, cfg["core"] = cfg.get("core"), None
        cfg["as"], cfg["cpu"], cfg["stack"] = cfg.get("int_as"), cfg.get("int_cpu"), cfg.get("int_as")
        child(cfg["interactor"], a_r, b_w, err, cfg["cwd"])
    for fd in (a_r, a_w, b_r, b_w):
        os.close(fd)
    pids += [p_sol, p_int]
    signal.setitimer(signal.ITIMER_REAL, cfg["wall"])
    res = {}
    while len(res) < 2:
        pid, status, ru = os.wait4(-1, 0)
        res[pid] = (status, ru)
    signal.setitimer(signal.ITIMER_REAL, 0)
    st, ru = res[p_sol]
    ist, iru = res[p_int]
    out = {"cpu": ru.ru_utime + ru.ru_stime, "wall": time.perf_counter() - t0, "rss_kb": ru.ru_maxrss, "status": st,
           "timeout": bool(timed_out), "int_status": ist}
else:
    fin = os.open(cfg["stdin"], os.O_RDONLY)
    fout = os.open(cfg["stdout"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    ferr = os.open(cfg["stderr"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC) if cfg.get("stderr") else null
    pid = os.fork()
    if pid == 0:
        child(cfg["argv"], fin, fout, ferr, cfg["cwd"])
    pids.append(pid)
    signal.setitimer(signal.ITIMER_REAL, cfg["wall"])
    _, status, ru = os.wait4(pid, 0)
    signal.setitimer(signal.ITIMER_REAL, 0)
    out = {"cpu": ru.ru_utime + ru.ru_stime, "wall": time.perf_counter() - t0, "rss_kb": ru.ru_maxrss,
           "status": status, "timeout": bool(timed_out)}
if sys.platform == "darwin":
    out["rss_kb"] //= 1024  # macOS reports bytes
print(json.dumps(out))
'''


def run(argv, stdin, stdout, cwd, tl, ml_mb, core=None, stderr=None, interactor=None, launcher=None):
    """Run argv once under limits: CPU limit tl seconds (killed at 2*tl+1 wall), memory ml_mb. Returns the launcher's
    dict plus "verdict" in {ok, TLE, MLE, RE} (RE covers a nonzero exit or a signal)."""
    ml = ml_mb << 20
    cfg = {"argv": argv, "stdin": stdin, "stdout": stdout, "stderr": stderr, "cwd": cwd, "core": core,
           "as": ml + (64 << 20), "stack": ml, "cpu": int(math.ceil(tl)) + 1, "fsize": OUT_LIMIT,
           "wall": 2 * tl + 1}
    if interactor:
        cfg.update(interactor=interactor, int_as=4 * ml + (64 << 20), int_cpu=int(math.ceil(4 * tl)) + 2)
    p = subprocess.run([launcher or PYTHON, "-I", "-S", "-c", LAUNCHER, json.dumps(cfg)], capture_output=True,
                       text=True)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"verdict": "RE", "error": (p.stderr or "launcher failed")[-500:], "cpu": 0.0, "wall": 0.0,
                "rss_kb": 0}
    st = r["status"]
    if r["timeout"] or r["cpu"] > tl or (os.WIFSIGNALED(st) and os.WTERMSIG(st) in (9, 24)):  # SIGKILL / SIGXCPU
        r["verdict"] = "TLE" if r["cpu"] > tl * 0.99 or r["timeout"] else "RE"
    elif r["rss_kb"] > ml_mb * 1024:
        r["verdict"] = "MLE"
    elif os.WIFSIGNALED(st) or os.WEXITSTATUS(st) != 0:
        r["verdict"] = "RE"
    else:
        r["verdict"] = "ok"
    return r


def compile_cpp(sources, out, includes=(), flags=None, timeout=120):
    """g++ sources -> out. Returns (ok, last 2000 chars of the compiler output)."""
    cmd = [CXX, *(flags or CXXFLAGS), *[f"-I{d}" for d in includes], *sources, "-o", out]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "compile timeout"
    return p.returncode == 0, (p.stdout + p.stderr)[-2000:]


def tokens_equal(out_path, ans_path):
    """Whitespace-insensitive token comparison (USACO's rule for problems without a special checker)."""
    with open(out_path, "rb") as a, open(ans_path, "rb") as b:
        return a.read().split() == b.read().split()


def run_checker(kind, binary, inp, out, ans, cwd):
    """Score in [0, 1] of one output, for the checker conventions of the sources:
    cms      checker <input> <correct output> <contestant output>; stdout = score (EGOI, IOI)
    testlib  chk <input> <contestant output> <answer>; exit 0 = accepted, 7 = points; "Ratio: x" in its output is
             the score (FrontierCS, whose judge_engine.js scores the same way)."""
    if kind == "cms":
        p = subprocess.run([binary, inp, ans, out], capture_output=True, text=True, cwd=cwd, timeout=60)
        try:
            return max(0.0, min(1.0, float(p.stdout.split()[0]))), p.stderr.strip()[:300]
        except (IndexError, ValueError):
            return 0.0, ("checker failed: " + p.stderr)[:300]
    p = subprocess.run([binary, inp, out, ans], capture_output=True, text=True, cwd=cwd, timeout=60)
    msg = p.stdout or p.stderr or ""
    if p.returncode not in (0, 7):
        return 0.0, msg.strip()[:300]
    m = re.search(r"Ratio: ([\d.]+)", msg)
    return (float(m.group(1)) if m else (1.0 if p.returncode == 0 else 0.0)), msg.strip()[:300]


def interactor_score(status, msg):
    """FrontierCS interactive cases: the interactor's exit status and "Ratio:" decide, as for a testlib checker."""
    code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
    if code not in (0, 7):
        return 0.0
    m = re.search(r"Ratio: ([\d.]+)", msg or "")
    return float(m.group(1)) if m else (1.0 if code == 0 else 0.0)


# ---------------------------------------------------------------- scoring

def problem_score(meta, test_scores):
    """test name -> score in [0, 1] (0 for a failed run) -> problem score in [0, 100] by the source's rule:
    tests     every test counts the same (USACO: each test case is worth the same points)
    groupmin  subtasks of tests, a subtask scores max_score x the minimum over its tests (CMS GroupMin: EGOI, IOI)
    mean      mean of the test ratios x 100 (FrontierCS)"""
    sc = meta["scoring"]
    tests = [t["name"] for t in meta["tests"]]
    if sc["type"] in ("tests", "mean"):
        return 100.0 * sum(test_scores.get(t, 0.0) for t in tests) / len(tests) if tests else 0.0
    total = sum(g["max_score"] for g in sc["groups"]) or 1.0
    got = sum(g["max_score"] * min((test_scores.get(t, 0.0) for t in g["tests"]), default=0.0) for g in sc["groups"])
    return 100.0 * got / total


def solved(meta, test_scores):
    return all(test_scores.get(t["name"], 0.0) >= 1.0 - 1e-9 for t in meta["tests"])


def tmpdir(prefix):
    return tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("LADDER_TMP") or None)
