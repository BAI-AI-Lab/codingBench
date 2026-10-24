"""Static code quality profile of a finished LiveCodeBench run, following Huang et al., "Beyond Functional Correctness:
Static Code Quality Profiling of LLM-Generated Code" (arXiv:2610.19167, ICECCS 2026).

  python lcb_quality.py <run dir> [--sonar] [--workers 16]      # writes <run dir>/quality.jsonl and quality.md

Each answer (code_list[0]) is analyzed as-is, as in the paper: no imports are added, so a LeetCode answer that uses
List without importing it gets Pylint's undefined-variable error there too. Empty answers are skipped.
  Pylint 3.3.5, default configuration: message counts per type (convention, refactor, warning, error, fatal) and the
          0-10 score (None when the file does not parse)
  Radon 6.0.1 CLI: `cc -s -j` complexity = sum over every entry and function count = number of entries (the paper's
          rule: a class and each of its methods are separate entries), `mi -s -j`, `raw -s -j` (loc, lloc, sloc,
          comments, blank)
  SonarQube (--sonar, needs SONAR_URL and SONAR_TOKEN; the paper used SonarQube 10.4 / SonarCloud): open issues per
          software quality (maintainability, reliability, security), plus type, severity and rule counts
The report has the paper's three tables: per-answer means over all answers and over correct ones, by difficulty, and
correct-only densities per 100 SLOC (sum of counts / sum of SLOC x 100); no composite score. Correct means the
re-judged verdict from <run dir>/rejudge.jsonl (cb rejudge) when it exists, else LCB's own.
"""
import argparse
import concurrent.futures
import glob
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

PYLINT_TYPES = ("convention", "refactor", "warning", "error", "fatal")
SONAR_QUALITIES = ("maintainability", "reliability", "security")
RADON_SIZES = ("loc", "lloc", "sloc", "comments", "blank")
DIFFS = ("easy", "medium", "hard")
HIGHER_BETTER = {"Pylint score", "MI"}
SIZES = {"Func", "LOC", "LLOC", "SLOC", "CMT", "BLN"}  # describe size only: no better direction
LEGEND = "↑ higher is better, ↓ lower is better; columns without an arrow describe size only."


def head(name):
    """A column header with its direction mark."""
    return name if name in SIZES else name + (" ↑" if name in HIGHER_BETTER else " ↓")


def parse_pylint(text):
    """Pylint --output-format=json2 -> {convention, ..., fatal, total, score, messages: {"C0103 invalid-name": n, ...}}."""
    d = json.loads(text)
    counts = d["statistics"]["messageTypeCount"]
    out = {t: counts.get(t, 0) for t in PYLINT_TYPES}
    out["total"] = sum(out.values()) + counts.get("info", 0)
    out["messages"] = {}
    for m in d["messages"]:
        k = f"{m['messageId']} {m['symbol']}"
        out["messages"][k] = out["messages"].get(k, 0) + 1
    parsed = not any(m["messageId"] == "E0001" for m in d["messages"])  # syntax error: the paper's run gets no score
    out["score"] = d["statistics"].get("score") if parsed else None
    return out


def parse_radon(cc_text, mi_text, raw_text):
    """Radon -j outputs of one file -> {complexity, functions, mi, loc, lloc, sloc, comments, blank}, or None."""
    # cc lists no file at all when it has no function or class (a top-level script): complexity 0, as in the paper
    cc, mi, raw = (next(iter(json.loads(t).values()), empty) for t, empty in ((cc_text, []), (mi_text, {}), (raw_text, {})))
    if isinstance(cc, dict) or "error" in mi or "error" in raw or not raw:  # radon reports a parse error as {"error": ...}
        return None
    out = {"complexity": sum(e.get("complexity", 0) for e in cc), "functions": len(cc), "mi": mi["mi"]}
    out.update({k: raw[k] for k in RADON_SIZES})
    return out


def analyze(code, timeout=120):
    d = tempfile.mkdtemp(prefix="cbq_")
    try:
        path = os.path.join(d, "answer.py")  # a neutral module name, like the paper's temp files
        open(path, "w").write(code)
        env = dict(os.environ, PYLINTHOME=os.path.join(d, ".pylint"))
        run = lambda *a: subprocess.run([sys.executable, "-m", *a], capture_output=True, text=True, cwd=d, env=env,
                                        timeout=timeout).stdout
        return {"pylint": parse_pylint(run("pylint", "--output-format=json2", "answer.py")),
                "radon": parse_radon(run("radon", "cc", "-s", "-j", "answer.py"), run("radon", "mi", "-s", "-j", "answer.py"),
                                     run("radon", "raw", "-s", "-j", "answer.py"))}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sonar(rows, project, url, token, scanner):
    """Scan every answer as <qid>.py in one SonarQube project; returns {qid: counts}."""
    def api(path, data=None):
        req = urllib.request.Request(url.rstrip("/") + path, data=urllib.parse.urlencode(data).encode() if data else None)
        req.add_header("Authorization", "Bearer " + token)
        return json.load(urllib.request.urlopen(req, timeout=60))

    d = tempfile.mkdtemp(prefix="cbsonar_")
    try:
        for r in rows:
            open(os.path.join(d, r["question_id"] + ".py"), "w").write(r["code_list"][0])
        subprocess.run([scanner, f"-Dsonar.projectKey={project}", "-Dsonar.sources=.", f"-Dsonar.host.url={url}",
                        f"-Dsonar.token={token}", "-Dsonar.scm.disabled=true", "-Dsonar.python.version=3.12"],
                       cwd=d, check=True, capture_output=True, text=True)
        task = dict(l.split("=", 1) for l in open(os.path.join(d, ".scannerwork", "report-task.txt")).read().split()
                    if "=" in l)["ceTaskId"]
        while (status := api(f"/api/ce/task?id={task}")["task"]["status"]) in ("PENDING", "IN_PROGRESS"):
            time.sleep(2)
        if status != "SUCCESS":
            raise SystemExit(f"SonarQube analysis {status}")
        issues, page = [], 1
        while True:
            r = api(f"/api/issues/search?componentKeys={urllib.parse.quote(project)}&resolved=false&ps=500&p={page}")
            issues += r["issues"]
            if page * 500 >= r["paging"]["total"]:
                break
            page += 1
    finally:
        shutil.rmtree(d, ignore_errors=True)
    out = {r["question_id"]: {**{q: 0 for q in SONAR_QUALITIES}, "types": {}, "severities": {}, "rules": {}} for r in rows}
    for i in issues:
        q = i["component"].split(":", 1)[1].rsplit("/", 1)[-1].removesuffix(".py")
        if q not in out:
            continue
        for imp in i.get("impacts", []):
            out[q][imp["softwareQuality"].lower()] += 1
        out[q]["types"][i.get("type", "?")] = out[q]["types"].get(i.get("type", "?"), 0) + 1
        out[q]["severities"][i.get("severity", "?")] = out[q]["severities"].get(i.get("severity", "?"), 0) + 1
        out[q]["rules"][i["rule"]] = out[q]["rules"].get(i["rule"], 0) + 1
    return out


def summarize(recs, sonar_on):
    """Tables of the paper as Markdown: raw means (all, correct-only) by difficulty, correct-only density per 100 SLOC."""
    def cols():
        c = [("Pylint total", lambda r: r["pylint"]["total"])] + [(f"Pylint {t[0].upper()}", lambda r, t=t: r["pylint"][t])
                                                                    for t in PYLINT_TYPES[:4]]
        c += [("Pylint score", lambda r: r["pylint"]["score"]), ("CC", lambda r: r["radon"]["complexity"]),
              ("MI", lambda r: r["radon"]["mi"]), ("Func", lambda r: r["radon"]["functions"])]
        c += [(k.upper() if k != "comments" else "CMT", lambda r, k=k: r["radon"][k]) for k in RADON_SIZES]
        if sonar_on:
            c += [(f"Sonar {q[:5]}.", lambda r, q=q: r["sonar"][q]) for q in SONAR_QUALITIES]
        return c

    def mean(vals):
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None

    def fmt(v):
        return "—" if v is None else f"{v:.2f}"

    L = []
    for title, keep in (("All answers", lambda r: True), ("Correct answers only", lambda r: r["passed"])):
        L += [f"## {title}: mean per answer", "", LEGEND, "", "| difficulty | n | " + " | ".join(head(n) for n, _ in cols()) + " |",
              "|---|---|" + "---|" * len(cols())]
        for dname in DIFFS + ("all",):
            g = [r for r in recs if keep(r) and r["radon"] and (dname == "all" or r["difficulty"] == dname)]
            if g:
                L.append(f"| {dname} | {len(g)} | " + " | ".join(fmt(mean(f(r) for r in g)) for _, f in cols()) + " |")
        L.append("")
    dens = [("Pylint total", lambda r: r["pylint"]["total"])] + [(f"Pylint {t[0].upper()}", lambda r, t=t: r["pylint"][t])
                                                                  for t in PYLINT_TYPES[:4]]
    dens += [("CC", lambda r: r["radon"]["complexity"]), ("Func", lambda r: r["radon"]["functions"])]
    if sonar_on:
        dens += [(f"Sonar {q[:5]}.", lambda r, q=q: r["sonar"][q]) for q in SONAR_QUALITIES]
    L += ["## Correct answers only: per 100 SLOC", "", LEGEND, "", "| difficulty | n | SLOC | " + " | ".join(head(n) for n, _ in dens) + " |",
          "|---|---|---|" + "---|" * len(dens)]
    for dname in DIFFS + ("all",):
        g = [r for r in recs if r["passed"] and r["radon"] and (dname == "all" or r["difficulty"] == dname)]
        sloc = sum(r["radon"]["sloc"] for r in g)
        if g and sloc:
            L.append(f"| {dname} | {len(g)} | {sloc} | " + " | ".join(f"{100 * sum(f(r) for r in g) / sloc:.2f}" for _, f in dens) + " |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", 16)))
    ap.add_argument("--sonar", action="store_true", help="also run SonarQube (SONAR_URL, SONAR_TOKEN, SONAR_SCANNER)")
    a = ap.parse_args()
    f = glob.glob(os.path.join(a.run_dir, "output", "*", "Scenario.codegeneration_*_eval_all.json"))
    if len(f) != 1:
        raise SystemExit(f"expected one *_eval_all.json under {a.run_dir}/output, found {len(f)}")
    rows = [r for r in json.load(open(f[0])) if r["code_list"] and r["code_list"][0].strip()]
    rj = os.path.join(a.run_dir, "rejudge.jsonl")
    verdict = {v["q"]: v["passed"] for v in map(json.loads, open(rj))} if os.path.exists(rj) else {}
    with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
        res = list(pool.map(lambda r: analyze(r["code_list"][0]), rows))
    son = {}
    if a.sonar:
        url, token = os.environ["SONAR_URL"], os.environ["SONAR_TOKEN"]
        scanner = os.environ.get("SONAR_SCANNER") or shutil.which("sonar-scanner") or "sonar-scanner"
        project = "cb-" + "-".join(os.path.normpath(a.run_dir).split(os.sep)[-2:]).replace(".", "_")
        son = sonar(rows, project, url, token, scanner)
    recs = []
    for r, x in zip(rows, res):
        q = r["question_id"]
        recs.append({"q": q, "platform": r["platform"], "difficulty": r["difficulty"],
                     "passed": verdict.get(q, bool(r["graded_list"][0])), **x, "sonar": son.get(q)})
    with open(os.path.join(a.run_dir, "quality.jsonl"), "w") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in recs))
    md = (f"# Static code quality: {a.run_dir}\n\nProtocol of arXiv:2610.19167 (Pylint 3.3.5 default config, Radon 6.0.1 CLI"
          f"{', SonarQube' if a.sonar else ''}); answers analyzed as-is; correct = "
          f"{'re-judged (rejudge.jsonl)' if verdict else 'LCB verdict'}.\n\n" + summarize(recs, a.sonar))
    open(os.path.join(a.run_dir, "quality.md"), "w").write(md)
    print(md)
    print("written", os.path.join(a.run_dir, "quality.jsonl"))


if __name__ == "__main__":
    main()
