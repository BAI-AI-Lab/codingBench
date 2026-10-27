"""Static code quality of the Python answers (L1-L2) of a ladder run, in the protocol of arXiv:2610.19167 (the
analyzers and versions of cb quality: Pylint 3.3.5 default config, Radon 6.0.1, optionally SonarQube 10.4).

  python ladder_quality.py <run dir> [--sonar] [--workers 16]     # writes <run dir>/quality.jsonl

C++ answers (L3-L5) get no static-quality profile: the protocol's analyzers are Python-only and SonarQube 10.4
Community does not analyze C/C++.
"""
import argparse
import concurrent.futures
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lcb_quality as Q  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--sonar", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    last = {}
    for l in open(os.path.join(a.run_dir, "answers.jsonl")):
        r = json.loads(l)
        last[r["q"]] = r
    judged = {}
    jp = os.path.join(a.run_dir, "judge.jsonl")
    if os.path.exists(jp):
        for l in open(jp):
            r = json.loads(l)
            judged[r["q"]] = r
    rows = [r for r in last.values() if r["lang"] == "python" and r.get("code", "").strip()]
    with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda r: Q.analyze(r["code"]), rows))
    son = {}
    if a.sonar and rows:
        url, token = os.environ["SONAR_URL"], os.environ["SONAR_TOKEN"]
        scanner = os.environ.get("SONAR_SCANNER", "sonar-scanner")
        project = "ladder_" + os.path.basename(os.path.dirname(os.path.abspath(a.run_dir))).replace("/", "_")
        son = Q.sonar([{"question_id": r["q"].replace("#", "_"), "code_list": [r["code"]]} for r in rows], project, url,
                      token, scanner)
    with open(os.path.join(a.run_dir, "quality.jsonl"), "w") as f:
        for r, q in zip(rows, res):
            rec = {"q": r["q"], "pid": r["pid"], "tier": r["tier"], "solved": judged.get(r["q"], {}).get("solved"), **q}
            if son:
                rec["sonar"] = son.get(r["q"].replace("#", "_"))
            f.write(json.dumps(rec) + "\n")
    print(f"quality: {len(rows)} Python answers -> {a.run_dir}/quality.jsonl")


if __name__ == "__main__":
    main()
