"""Build the multimodal ladder: sample items from the source benchmarks (tools/mm_sources.py) and write them under
$CB/data/mm/items, plus the item list $CB/data/mm/mm.json (copy it to samples/mm.json to fix the set).

  python mm_build.py [--sources mmmu_pro,charxiv] [--seed 0] [--dry-run] [--list]

Rows come from the Hugging Face datasets-server (/rows, which returns images as links), so only the sampled items are
downloaded, never whole datasets. HF_TOKEN is sent when set (gated sets such as ZeroBench need it, after accepting the
terms on the dataset page). The same seed gives the same items. An image over MAX_IMAGE_MB is re-encoded as JPEG
(needs Pillow) or the item is skipped; images and frames are never committed, since several sources allow academic
use only. Video sources download only the sampled videos and keep FRAMES evenly spaced frames (needs ffmpeg).
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mm_lib as M  # noqa: E402
import mm_sources as S  # noqa: E402

DS = os.environ.get("HF_DATASETS_SERVER", "https://datasets-server.huggingface.co")
HUB = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
MAX_IMAGE_MB = float(os.environ.get("MM_MAX_IMAGE_MB", "7"))  # MiniMax takes images up to 10 MB; base64 adds a third
FRAMES = int(os.environ.get("MM_FRAMES", "16"))


def get(url, binary=False, tries=6):
    headers = {"User-Agent": "codingBench-mm"}
    host = urllib.parse.urlparse(url).hostname or ""
    if os.environ.get("HF_TOKEN") and (host == "huggingface.co" or host.endswith(".huggingface.co")):
        headers["Authorization"] = f"Bearer {os.environ['HF_TOKEN']}"  # never to a mirror or a CDN
    for i in range(tries):
        wait = 3 * 2 ** i
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404) or i == tries - 1:
                raise
            if e.code == 429:  # the datasets-server rate limit: wait as told, else a minute and more
                wait = max(int(e.headers.get("Retry-After") or 0), 60 * (i + 1))
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(wait)


def rows(dataset, config, split, offset, length=1):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length})
    return [r["row"] for r in get(f"{DS}/rows?{q}")["rows"]]


def num_rows(dataset, config, split):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config})
    for s in get(f"{DS}/size?{q}")["size"]["splits"]:
        if s["split"] == split:
            return s["num_rows"]
    raise KeyError(f"{dataset} {config}: no split {split}")


def hub_file(dataset, path):
    return f"{HUB}/datasets/{dataset}/resolve/main/{urllib.parse.quote(path)}"


def save_image(src, path):
    """Download an image link (or copy bytes); re-encode as JPEG when it is over the size limit. Returns the file name
    written, or None when it is too big and Pillow is missing."""
    data = src if isinstance(src, bytes) else get(src, binary=True)
    ext = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"RIFF": ".webp", b"GIF8": ".gif"}
    suffix = next((e for sig, e in ext.items() if data.startswith(sig)), None)
    if suffix and len(data) <= MAX_IMAGE_MB * 2 ** 20:
        open(path + suffix, "wb").write(data)
        return os.path.basename(path + suffix)
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    im = Image.open(io.BytesIO(data)).convert("RGB")
    for q in (92, 85, 75):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        if buf.tell() <= MAX_IMAGE_MB * 2 ** 20:
            open(path + ".jpg", "wb").write(buf.getvalue())
            return os.path.basename(path + ".jpg")
    return None


def image_size(path):
    """(width, height) of a PNG/JPEG/WEBP/GIF without Pillow when possible."""
    try:
        from PIL import Image
        return list(Image.open(path).size)
    except ImportError:
        pass
    b = open(path, "rb").read(64 * 1024)
    if b.startswith(b"\x89PNG"):
        return [int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")]
    if b.startswith(b"GIF8"):
        return [int.from_bytes(b[6:8], "little"), int.from_bytes(b[8:10], "little")]
    if b.startswith(b"\xff\xd8"):
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            marker, size = b[i + 1], int.from_bytes(b[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                return [int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")]
            i += 2 + size
    raise ValueError(f"cannot read the size of {path} (install Pillow)")


def frames(video, out_dir, n=FRAMES):
    """n frames evenly spaced over the video (centres of n equal segments), as frame00.jpg ...; needs ffmpeg/ffprobe."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True, check=True).stdout.strip())
    names = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        name = f"frame{i:02d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                        "scale='min(1280,iw)':-2", "-q:v", "3", os.path.join(out_dir, name)], check=True)
        names.append(name)
    return names


def mask_runs(data):
    """{row: [[x0, x1], ...]} of the non-zero pixels of a mask image, and its [width, height]."""
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("L")
    w, h = im.size
    px = im.load()
    runs = {}
    for y in range(h):
        x, r = 0, []
        while x < w:
            if px[x, y]:
                x0 = x
                while x < w and px[x, y]:
                    x += 1
                r.append([x0, x])
            x += 1
        if r:
            runs[str(y)] = r
    return runs, [w, h]


def write_item(it, media):
    """media: [("image", url or bytes)] or [("video", url)], or a function giving that list (links looked up only for
    the items kept); writes the files and item.json; False if skipped."""
    d = M.item_dir(it["id"])
    tmp = d + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        it["images"], it["frames"] = [], []
        for i, (kind, src) in enumerate(media() if callable(media) else media):
            if kind == "image":
                f = save_image(src, os.path.join(tmp, f"img{i}"))
                if not f:
                    return False
                it["images"].append(f)
            else:
                with tempfile.NamedTemporaryFile(suffix=".mp4") as v:
                    v.write(get(src, binary=True))
                    v.flush()
                    it["frames"] = frames(v.name, tmp)
        if it.get("mask_src"):  # the target mask as runs per pixel row (needs Pillow)
            it["mask"], it["size"] = mask_runs(get(it.pop("mask_src"), binary=True))
        if it["answer_type"] == "point_in_box" and "size" not in it:
            it["size"] = image_size(os.path.join(tmp, it["images"][0]))
        json.dump(it, open(os.path.join(tmp, "item.json"), "w"), ensure_ascii=False, indent=1)
        shutil.rmtree(d, ignore_errors=True)
        os.replace(tmp, d)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def missing(src):
    """The tools a source needs that are not installed here."""
    out = []
    for n in src.get("needs", []):
        if n == "ffmpeg" and not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            out.append("ffmpeg")
        if n == "pillow":
            try:
                import PIL  # noqa: F401
            except ImportError:
                out.append("Pillow")
    return out


def build(src, seed, dry):
    """Sample src["n"] usable items from a source, spread over its parts (configs / splits); returns the item ids."""
    rng = random.Random(f"{seed}:{src['name']}")
    parts = src["parts"]
    quota = [src["n"] // len(parts) + (i < src["n"] % len(parts)) for i in range(len(parts))]
    ids = []
    for (config, split), want in zip(parts, quota):
        # candidate rows: the Hub annotation files of the source, else whole datasets-server pages (100 rows; images
        # come as links) in random page order, until there are enough usable rows (a stratified source reads them all)
        cand = []
        if src.get("rows"):
            loaded = src["rows"]((config, split))
            total = len(loaded)
            cand = [(o, r) for o, r in enumerate(loaded)]
            cand = [(o, m) for o, r in cand for m in [src["adapt"](r, config, split, o)] if m]
        else:
            total = num_rows(src["hf"], config, split)
            pages = list(range(0, total, 100))
            rng.shuffle(pages)
            for o in pages:
                page = rows(src["hf"], config, split, o, 100)
                cand += [(o + i, m) for i, r in enumerate(page) for m in [src["adapt"](r, config, split, o + i)] if m]
                if not src.get("stratum") and len(cand) >= 3 * want:
                    break
        rng.shuffle(cand)
        if src.get("stratum"):  # round-robin over the strata
            groups = {}
            for c in cand:
                groups.setdefault(src["stratum"](c[1][0]), []).append(c)
            gs = [groups[k] for k in sorted(groups)]
            cand = [g[i] for i in range(max(map(len, gs), default=0)) for g in gs if i < len(g)]
        got = 0
        for off, (it, media) in cand:
            if got >= want:
                break
            it.update(source=src["name"], capability=src["cap"], tier=it.get("tier") or src["tier"])
            it["id"] = f"{src['name']}/{config}/{split}/{off}".replace(" ", "_")
            try:
                ok = dry or write_item(it, media)
            except (urllib.error.URLError, subprocess.CalledProcessError, ValueError, OSError) as e:
                # an expired link, a missing file, a broken video: skip the item, take the next candidate
                print(f"  skip {it['id']}: {repr(e)[:160]}", flush=True)
                ok = False
            if ok:
                ids.append(it["id"])
                got += 1
        print(f"{src['name']} {config}/{split}: {got} of {want} items (of {total} rows)", flush=True)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="sample and check the rows, download nothing")
    ap.add_argument("--list", action="store_true", help="show the sources and stop")
    a = ap.parse_args()
    if a.list:
        for s in S.SOURCES:
            print(f"{s['name']:<16} {s['cap']:<11} {s['tier']}  n={s['n']:<3} {s['hf']}  {s.get('note', '')}")
        return
    want = set(filter(None, a.sources.split(",")))
    man_path = os.path.join(M.DATA, "mm.json")
    man = json.load(open(man_path)) if os.path.exists(man_path) else {"capabilities": {}, "sources": {}}
    for s in S.SOURCES:
        if want and s["name"] not in want:
            continue
        if missing(s) and not a.dry_run:
            print(f"{s['name']}: SKIPPED (install {', '.join(missing(s))})", flush=True)
            continue
        try:
            ids = build(s, a.seed, a.dry_run)
        except urllib.error.HTTPError as e:  # gated without access, renamed, down: the other sources go on
            print(f"{s['name']}: SKIPPED ({e.code} {e.reason}){' - ' + s['note'] if s.get('note') else ''}", flush=True)
            continue
        if a.dry_run:
            continue
        caps = man["capabilities"]
        caps[s["cap"]] = [i for i in caps.get(s["cap"], []) if not i.startswith(s["name"] + "/")] + ids
        man["sources"][s["name"]] = {"hf": s["hf"], "cap": s["cap"], "tier": s["tier"], "n": len(ids),
                                     "license": s.get("license"), "seed": a.seed}
        man["version"] = time.strftime("%Y-%m-%d")
        os.makedirs(M.DATA, exist_ok=True)
        json.dump(man, open(man_path + ".tmp", "w"), ensure_ascii=False, indent=1)
        os.replace(man_path + ".tmp", man_path)
    if not a.dry_run:
        print(f"item list: {man_path} ({sum(len(v) for v in man['capabilities'].values())} items)")


if __name__ == "__main__":
    main()
