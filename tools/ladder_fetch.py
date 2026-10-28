"""Portable, verified download of the ladder test set (any OS with Python 3.8+), and verification of a copy.

  python tools/ladder_fetch.py samples/ladder_download.tsv.gz <dest dir> [--workers 16]
  python tools/ladder_fetch.py samples/ladder_download.tsv.gz <dest dir> --verify [--delete-bad]

Use it where the link is fast (e.g. a laptop), then push the dest dir to the server's data/ladder/raw with rsync;
cb ladder-data (tools/ladder_download.sh) is the server-side alternative. Every file is checked: size; git blob sha1
for GitHub files (the hash in the list, from the pinned trees); a CRC test for zip files. Partial files resume
(HTTP Range); a file that fails its check is downloaded again. --verify only checks what is in <dest dir> (e.g. a
copy on the server) and lists missing or bad files.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile

UA = {"User-Agent": "Mozilla/5.0 (codingBench; academic benchmark)"}
_lock = threading.Lock()
_done = {"files": 0, "bytes": 0}


def rows(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3:
                yield p[0], p[1], int(p[2]), (p[3] if len(p) > 3 else "")


def check(path, size, sha):
    """None if the file is complete and correct, else the reason."""
    if not os.path.isfile(path):
        return "missing"
    n = os.path.getsize(path)
    if size >= 0 and n != size:
        return f"size {n} != {size}"
    if size < 0 and n == 0:
        return "empty"
    if sha:
        h = hashlib.sha1(b"blob %d\0" % n)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha:
            return "git sha1 mismatch"
    if path.endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
            if bad:
                return f"zip CRC error in {bad}"
        except zipfile.BadZipFile as e:
            return f"bad zip: {e}"
    return None


def fetch(url, path, size, sha, tries=8):
    if check(path, size, sha) is None:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + ".part"
    for i in range(tries):
        try:
            have = os.path.getsize(part) if os.path.exists(part) and size >= 0 else 0
            if size >= 0 and have > size:
                os.remove(part)
                have = 0
            h = dict(UA)
            if have:
                h["Range"] = f"bytes={have}-"
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                mode = "ab" if have and r.status == 206 else "wb"
                with open(part, mode) as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                        with _lock:
                            _done["bytes"] += len(b)
            os.replace(part, path)
            why = check(path, size, sha)
            if why is None:
                with _lock:
                    _done["files"] += 1
                return None
            os.remove(path)  # complete but wrong: start over
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            why = repr(e)[:200]
        time.sleep(min(60, 2 ** i))
    return why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("dest")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--delete-bad", action="store_true")
    a = ap.parse_args()
    todo = list(rows(a.list))
    total = sum(max(s, 0) for _, _, s, _ in todo)
    t0 = time.time()
    if a.verify:
        with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda r: (r[1], check(os.path.join(a.dest, r[1]), r[2], r[3])), todo))
        bad = [(p, w) for p, w in res if w]
        for p, w in bad[:50]:
            print(f"BAD {p}: {w}")
        if a.delete_bad:
            for p, w in bad:
                if w != "missing":
                    os.remove(os.path.join(a.dest, p))
        print(f"verified {len(todo) - len(bad)}/{len(todo)} files; {len(bad)} missing or bad "
              f"({sum(w == 'missing' for _, w in bad)} missing) in {time.time() - t0:.0f} s")
        sys.exit(1 if bad else 0)
    failed = []

    def one(r):
        url, rel, size, sha = r
        why = fetch(url, os.path.join(a.dest, rel), size, sha)
        if why:
            failed.append((rel, why))

    def progress():
        while not stop.is_set():
            stop.wait(30)
            dt = time.time() - t0
            print(f"[{dt:5.0f} s] {_done['files']} files, {_done['bytes'] / 1e6:.0f} MB downloaded, "
                  f"{_done['bytes'] / 1e6 / max(dt, 1):.1f} MB/s", flush=True)
    stop = threading.Event()
    reporter = threading.Thread(target=progress)
    reporter.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
            list(ex.map(one, todo))
    finally:
        stop.set()
        reporter.join()
    dt = time.time() - t0
    print(f"done in {dt:.0f} s: {_done['bytes'] / 1e6:.0f} MB downloaded ({_done['bytes'] / 1e6 / max(dt, 1):.1f} MB/s), "
          f"list total {total / 1e6:.0f} MB, {len(failed)} failed")
    for rel, why in failed[:30]:
        print(f"FAILED {rel}: {why}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
