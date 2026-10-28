"""Write the download list of the ladder test set (samples/ladder_download.tsv.gz) from the pinned sources.

  python tools/ladder_sources.py [--out samples/ladder_download.tsv.gz]      # needs fast access to usaco.org and GitHub

Run it where the internet is fast; the list is committed, and cb ladder-data downloads
it on the server with tools/ladder_download.sh (resumable), or tools/ladder_fetch.py downloads it anywhere (e.g. a
laptop with a fast link) and rsync pushes it. Lines: url, path under data/ladder/raw, size (-1 = unknown), git blob
sha1 of GitHub files (empty for USACO), in the order USACO Bronze -> Platinum, EGOI 2026, IOI 2026, FrontierCS.
Set GITHUB_TOKEN to avoid API rate limits.
To add a contest or a new USACO season: add it here, re-run, commit, then cb ladder-data and cb ladder-build.
"""
import argparse
import gzip
import json
import os
import re
import time
import urllib.request

USACO_PAGES = ["dec24results", "jan25results", "feb25results", "open25results",
               "season26contest1results", "season26contest2results", "season26contest3results"]
REPOS = {  # name -> (GitHub repo, pinned commit, path prefix to keep, files to skip)
    "egoi2026": ("egoi-org/egoi-2026", "08eedd32c99edf2223ea3987744898f7b774cb47", ""),
    "ioi2026": ("ioi/task-archive", "70278dfa33e30fe9a2d996c779ab37aafab29e67", "2026/"),
    "frontiercs": ("FrontierCS/Frontier-CS", "12ab26840cff15f1d0ab09004dafd07f92c14b60", ""),
}
UA = {"User-Agent": "Mozilla/5.0 (codingBench; academic benchmark)"}
DIVISIONS = ("bronze", "silver", "gold", "platinum")


def get(url, method="GET"):
    h = dict(UA)
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return urllib.request.urlopen(urllib.request.Request(url, headers=h, method=method), timeout=60)


def keep(name, path):
    """Which files of a repo the ladder needs."""
    if name == "egoi2026":  # statements: English only (Typst source + PDF) and the sample files
        return "/statement/" not in path or "english" in path or re.search(r"\.(input|output)\d+\.txt$", path)
    if name == "ioi2026":
        return "/translations/" not in path and not path.endswith(".DS_Store")
    return (path.startswith(("algorithmic/problems/", "algorithmic/judge/", "results/", "leaderboard/"))
            or path in ("README.md", "LICENSE"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples/ladder_download.tsv.gz")
    a = ap.parse_args()
    rows = {d: [] for d in DIVISIONS}
    for page in USACO_PAGES:
        url = f"https://usaco.org/index.php?page={page}"
        h = get(url).read().decode("utf-8", "replace")
        rows["bronze"].append((url, f"usaco/pages/{page}.html", -1, ""))
        for m in re.finditer(r"cpid=(\d+)'>View problem</a>.*?href='(current/data/[^']+\.zip)'.*?href='(current/data/sol_[^']+\.html)'", h, re.S):
            cpid, z, sol = m.groups()
            div = re.search(r"_(bronze|silver|gold|platinum)_", z).group(1)
            size = int(get("https://usaco.org/" + z, "HEAD").headers.get("Content-Length", -1))
            rows[div] += [(f"https://usaco.org/index.php?page=viewproblem2&cpid={cpid}", f"usaco/{cpid}/problem.html", -1, ""),
                          (f"https://usaco.org/{sol}", f"usaco/{cpid}/solution.html", -1, ""),
                          (f"https://usaco.org/{z}", f"usaco/{cpid}/tests.zip", size, "")]
        time.sleep(1)
    out = [r for d in DIVISIONS for r in rows[d]]
    for name, (repo, sha, prefix) in REPOS.items():
        tree = json.load(get(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1"))
        if tree.get("truncated"):
            raise SystemExit(f"{repo}: tree truncated")
        for x in tree["tree"]:
            p = x["path"]
            if x["type"] != "blob" or not p.startswith(prefix) or not keep(name, p[len(prefix):]):
                continue
            out.append((f"https://raw.githubusercontent.com/{repo}/{sha}/{p}", f"{name}/{p[len(prefix):]}", x["size"], x["sha"]))
    with gzip.open(a.out, "wt") as f:
        for u, d, s, h in out:
            f.write(f"{u}\t{d}\t{s}\t{h}\n")
    total = sum(max(r[2], 0) for r in out)
    print(f"{a.out}: {len(out)} files, {total / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
