"""Shared pieces of the multimodal ladder (cb mm): paths, the item files, prompts, answer extraction and scoring.

An item lives in $CB/data/mm/items/<item dir>/ (written by mm_build.py; never committed or published, because several
sources allow academic use only):
  item.json   id, source, capability, tier, question, options, answer, answer type, image / frame file names, extra
              fields a scorer needs (a target box, the image size, an answer range)
  *.png/jpg   the images, or the frames of a video (every model gets the same frames, so video scores are comparable)

Every model answers the same items; a capability's score is the mean over its items of the per-item mean over the
samples, each scored 0-1. The overall score weighs the capabilities equally (see mm_report.py).
"""
import base64
import json
import math
import os
import re

CB = os.environ.get("CB", "/data/hx/code_bench")
DATA = os.path.join(CB, "data", "mm")
ITEMS = os.path.join(DATA, "items")
TIERS = ("L1", "L2", "L3", "L4")
CAPS = ("reasoning", "perception", "charts", "documents", "spatial", "gui", "video")
CAP_NAME = {"reasoning": "视觉推理", "perception": "视觉感知", "charts": "图表", "documents": "文档", "spatial": "空间",
            "gui": "界面定位", "video": "视频理解"}
TIER_NAME = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖"}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def item_dir(iid):
    """Item ids look like "mmmu_pro/standard/test/123"; on disk the slashes become "__"."""
    return os.path.join(ITEMS, iid.replace("/", "__"))


def load_item(iid):
    return json.load(open(os.path.join(item_dir(iid), "item.json")))


def load_manifest(path):
    """samples/mm.json -> {"capabilities": {cap: [item id, ...]}, ...}"""
    return json.load(open(path))


# ---------------------------------------------------------------- prompts

SYSTEM = None  # no system prompt: every model gets the same user message

ASK = {
    "mcq": "Answer with the letter of the correct option. End your reply with a line of the form \"Answer: X\".",
    "yesno": "Answer yes or no. End your reply with a line of the form \"Answer: yes\" or \"Answer: no\".",
    "short": "Answer with a single word, number or short phrase. End your reply with a line of the form "
             "\"Answer: <your answer>\".",
    "point": "Give the point as relative coordinates: x from the left edge and y from the top edge of the image, each "
             "an integer from 0 to 1000. End your reply with a line of the form \"Answer: (x, y)\".",
}
KIND = {"mcq": "mcq", "yesno": "yesno", "exact": "short", "number": "short", "anls": "short", "point_in_box": "point",
        "point_in_mask": "point"}


def prompt_text(it):
    """The text part of the user message: question, lettered options, and how to give the answer."""
    parts = [it["question"].strip()]
    if it.get("options"):
        parts.append("\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(it["options"])))
    parts.append(ASK[KIND[it["answer_type"]]])
    return "\n\n".join(parts)


def data_url(path):
    mime = MIME.get(os.path.splitext(path)[1].lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def messages(it, detail=None):
    """(messages for the API, the same messages with images replaced by their file names for the logs).
    Images (or video frames, in order) come before the text, as in MMMU-Pro's protocol."""
    d = item_dir(it["id"])
    content, logged = [], []
    if it.get("frames"):
        content.append({"type": "text", "text": f"The following {len(it['frames'])} images are frames sampled "
                                                "uniformly from a video, in order."})
        logged.append(content[-1])
    for f in it.get("images", []) + it.get("frames", []):
        part = {"url": data_url(os.path.join(d, f))}
        if detail:
            part["detail"] = detail
        content.append({"type": "image_url", "image_url": part})
        logged.append({"type": "image_url", "image_url": {"url": f"file:{f}"}})
    text = {"type": "text", "text": prompt_text(it)}
    return [{"role": "user", "content": content + [text]}], [{"role": "user", "content": logged + [text]}]


# ---------------------------------------------------------------- answers

def final_answer(text):
    """What follows the last "Answer:" (or "答案："), else the last non-empty line; markdown and LaTeX wrapping
    removed. None when the reply is empty."""
    t = (text or "").strip()
    if not t:
        return None
    m = list(re.finditer(r"(?:\*\*)?(?:final\s+)?answer(?:\*\*)?\s*[:：]\s*(.+)", t, re.I)) or \
        list(re.finditer(r"答案\s*[:：]\s*(.+)", t))
    s = m[-1].group(1) if m else t.splitlines()[-1]
    s = re.sub(r"\\boxed\{(.*)\}", r"\1", s.strip())
    s = re.sub(r"\\text\{(.*?)\}", r"\1", s).strip().strip("*` ")
    m = re.fullmatch(r"\$+(.+?)\$+", s)  # LaTeX math $...$; a lone "$" is a currency sign and stays
    s = m.group(1) if m else s
    return s.strip().rstrip(".。").strip() or None


def parse_letter(s, n):
    """The option letter in an answer line: "B", "(B)", "B. text", "Option B"; None if there is no single letter
    among the first n."""
    if s is None:
        return None
    valid = LETTERS[:n]
    m = re.match(rf"^(?:\(([{valid}])\)|([{valid}])(?:[.:)](?:\s|$)|$))", s.strip())  # "(B) ...", "B. ...", "B"
    if m:
        return m.group(1) or m.group(2)
    found = set(re.findall(rf"\b([{valid}])\b", s))  # otherwise the one standalone letter ("Option D"; "A or B" is none)
    return found.pop() if len(found) == 1 else None


def norm(s):
    s = str(s).lower().strip()
    s = re.sub(r"[\"'`*_]", "", s)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = re.sub(r"[^\w\s.%-]", " ", s)
    return " ".join(s.split()).rstrip(".")


def to_number(s):
    """A number in a short answer ("3,200", "45%", "-0.5", "1/4"), or None."""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("−", "-").strip().rstrip("%").strip()
    m = re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?", t, re.I)
    if m:
        return float(t)
    m = re.fullmatch(r"([-+]?\d+)\s*/\s*(\d+)", t)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    return None


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def anls(pred, golds, tau=0.5):
    """Average Normalized Levenshtein Similarity of one answer (DocVQA): 1 - NL against the closest gold, 0 below tau."""
    p = " ".join(str(pred).lower().split())
    best = 0.0
    for g in golds:
        g = " ".join(str(g).lower().split())
        nl = levenshtein(p, g) / max(len(p), len(g), 1)
        best = max(best, 1 - nl if nl < tau else 0.0)
    return best


def parse_point(s):
    """(x, y) from "(512, 300)", "x=512, y=300", "[512, 300]"."""
    if s is None:
        return None
    nums = re.findall(r"-?\d+(?:\.\d+)?", s)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None


def score(it, text):
    """(score 0-1, the extracted answer or None when nothing could be read). An answer that cannot be read scores 0."""
    t = it["answer_type"]
    s = final_answer(text)
    gold = it.get("answer")
    golds = gold if isinstance(gold, list) else [gold]
    if t == "mcq":  # options listed by us, or written into the question / the image (n_options)
        got = parse_letter(s, len(it["options"]) if it.get("options") else it["n_options"])
        return (1.0 if got is not None and got == gold else 0.0), got
    if t == "yesno":
        got = (re.findall(r"\b(yes|no)\b", (s or "").lower()) or [None])[-1]
        return (1.0 if got is not None and got == str(gold).lower() else 0.0), got
    if t in ("exact", "number"):
        if s is None:
            return 0.0, None
        x = to_number(s)
        rng = it.get("range")  # an accepted interval [lo, hi] for a read-off value
        if rng and x is not None:
            return (1.0 if rng[0] <= x <= rng[1] else 0.0), s
        for g in golds:
            y = to_number(g)
            if x is not None and y is not None:
                tol = it.get("rel_tol", 0.01 if t == "number" else 0.0)
                if math.isclose(x, y, rel_tol=tol, abs_tol=1e-9):
                    return 1.0, s
            elif norm(s) == norm(g):
                return 1.0, s
        return 0.0, s
    if t == "anls":
        return (anls(s, golds) if s is not None else 0.0), s
    if t in ("point_in_box", "point_in_mask"):
        p = parse_point(s)
        if p is None:
            return 0.0, None
        w, h = it["size"]
        x, y = p
        if x <= 1 and y <= 1:  # fractions instead of 0-1000
            x, y = x * 1000, y * 1000
        x, y = x / 1000 * w, y / 1000 * h
        got = f"({p[0]:g}, {p[1]:g})"
        if t == "point_in_box":
            x1, y1, x2, y2 = it["box"]
            return (1.0 if x1 <= x <= x2 and y1 <= y <= y2 else 0.0), got
        row = int(min(max(y, 0), h - 1))  # mask: per pixel row, the [x0, x1) runs inside the target
        col = min(max(x, 0), w - 1)
        return (1.0 if any(x0 <= col < x1 for x0, x1 in it["mask"].get(str(row), [])) else 0.0), got
    raise ValueError(f"unknown answer type {t}")
