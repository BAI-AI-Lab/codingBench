"""Download the official English statements shown on the results site: python fetch_statements.py [paper dir].

  USACO       the problem page (usaco.org) and the figures it shows
  EGOI 2026   statement/english.pdf of egoi-org/egoi-2026 at the commit the problems were built from
  FrontierCS  statement.txt of FrontierCS/Frontier-CS at the same commit as the problems

Everything goes to data/statements_src/ (data/ is never committed); site.py renders it. Existing files are kept.
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "statements_src")
META = json.load(open(os.path.join(ROOT, "data", "dirs", "meta.json")))["meta"]
EGOI = "https://raw.githubusercontent.com/egoi-org/egoi-2026/08eedd32c99edf2223ea3987744898f7b774cb47"
FCS = "https://raw.githubusercontent.com/FrontierCS/Frontier-CS/12ab26840cff15f1d0ab09004dafd07f92c14b60/algorithmic/problems"
EGOI_DAY = {"biscuits": "day1", "ferriswheel": "day1", "ovenmasters": "day1", "cakes": "day2", "foxfamilies": "day2",
            "wateringplants": "day2"}


def get(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return open(dst, "rb").read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for k in range(4):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "codingBench"}), timeout=60).read()
            open(dst, "wb").write(data)
            return data
        except OSError:
            time.sleep(2 + 3 * k)
    raise SystemExit(f"failed: {url}")


n = 0
for pid in META:
    kind, rest = pid.split("-", 1)
    if kind == "usaco":
        h = get(f"https://usaco.org/index.php?page=viewproblem2&cpid={rest}", os.path.join(OUT, "usaco", f"{rest}.html")).decode("utf-8", "replace")
        body = (re.search(r'<span id="probtext-text"[^>]*>(.*?)</span>\s*</div>', h, re.S) or [None, ""])[1]
        for src in re.findall(r'<img[^>]*src=["\']([^"\']+)', body):
            url = src if src.startswith("http") else "https://usaco.org/" + src.lstrip("/")
            get(url, os.path.join(OUT, "usaco", "img", os.path.basename(src)))
    elif kind == "egoi26":
        get(f"{EGOI}/{EGOI_DAY[rest]}/{rest}/statement/english.pdf", os.path.join(OUT, "egoi", f"{rest}.pdf"))
    else:
        get(f"{FCS}/{rest}/statement.txt", os.path.join(OUT, "frontiercs", f"{rest}.txt"))
    n += 1
print(f"{n} statements in {OUT}")
