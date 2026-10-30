"""The source benchmarks of the multimodal ladder and how a row of each becomes an item (used by mm_build.py).

Each source: name, hf (dataset id), cap (capability), tier (L1-L4 by how saturated the source is for current models;
a source with its own difficulty labels sets the tier per item), n (items to sample), parts ([(config, split)], the
quota spread evenly over them), adapt(row, config, split, offset) -> (item fields, media) or None to skip the row,
and optionally rows(part) -> list of rows for sources the datasets-server cannot serve (annotation files on the Hub),
stratum(item) to spread the sample evenly over a field (the whole part is read first), needs (pillow / ffmpeg),
license and note.
Field names were checked against the datasets-server on 2026-10-29.

The capabilities are kept apart: each tests one skill with one answer format, and rows that would test another
capability's skill are left out. Subject reasoning has no tables, charts or screenshots and no question printed in the
image; perception has BLINK's low-level subtasks only (its depth, relation, multi-view and localization subtasks are
spatial, IQ_Test is abstract reasoning and left out); documents are text-dense pages without figures or infographics;
spatial is multiple choice only, so pointing belongs to GUI alone; GUI targets are icons, since a text target is
reading plus pointing; video is temporal (questions a single frame cannot answer), not expert knowledge from a video.
"""
import ast
import json
import os
import re
import urllib.parse

HUB = os.environ.get("HF_ENDPOINT", "https://huggingface.co")  # a mirror serves Hub files, not the datasets-server


def _hub(dataset, path):
    return f"{HUB}/datasets/{dataset}/resolve/main/{urllib.parse.quote(path)}"


def _imgs(row, keys):
    return [("image", row[k]["src"]) for k in keys if row.get(k)]


OTHER_CAP_IMAGES = {"Tables", "Plots and Charts", "Screenshots"}  # documents, charts, GUI


def mmmu_pro(row, config, split, off):
    opts = ast.literal_eval(row["options"])  # Python-repr lists, parsed as literals only
    if not opts or not row.get("answer") or OTHER_CAP_IMAGES & set(ast.literal_eval(row.get("img_type") or "[]")):
        return None
    tier = {"Easy": "L1", "Medium": "L2", "Hard": "L3"}.get(row.get("topic_difficulty"), "L2")
    keys = [f"image_{i}" for i in range(1, 8) if row.get(f"image_{i}")]
    # the datasets-server's image links for this config (a name with spaces and brackets) all return 403, so the
    # images come from the same question of the original MMMU (same id, same images)
    return ({"question": row["question"], "options": opts, "answer_type": "mcq", "answer": row["answer"], "tier": tier,
             "subject": row.get("subject")}, lambda: _mmmu_images(row["id"], keys))


def _mmmu_images(qid, keys):
    import mm_build
    split, rest = qid.split("_", 1)  # "test_Agriculture_195", "validation_Public_Health_27"
    subject, num = rest.rsplit("_", 1)
    found = mm_build.rows("MMMU/MMMU", subject, split, int(num) - 1)
    if not found or found[0]["id"] != qid:  # not in id order: look through the subject's rows of that split
        total = mm_build.num_rows("MMMU/MMMU", subject, split)
        found = [r for o in range(0, total, 100) for r in mm_build.rows("MMMU/MMMU", subject, split, o, 100) if r["id"] == qid]
    if not found:
        raise ValueError(f"{qid} not in MMMU/MMMU {subject} {split}")
    return _imgs(found[0], keys)


def blink(row, config, split, off):
    m = re.fullmatch(r"\(?([A-Z])\)?", row.get("answer") or "")  # "(B)", or "C" in Relative_Reflectance
    if not m:
        return None  # the test split hides its answers ("hidden")
    return ({"question": row["question"], "options": row["choices"], "answer_type": "mcq", "answer": m.group(1),
             "subtask": row.get("sub_task")}, _imgs(row, [f"image_{i}" for i in range(1, 5)]))


def cvbench(row, config, split, off):
    m = re.fullmatch(r"\(([A-Z])\)", row.get("answer") or "")
    if not m or not row.get("choices"):
        return None
    return ({"question": row["question"], "options": row["choices"], "answer_type": "mcq", "answer": m.group(1),
             "subtask": row.get("task")}, _imgs(row, ["image"]))


def charxiv(row, config, split, off):
    if not row.get("reasoning_a"):
        return None
    # reasoning_a_type: 1 text in chart, 2 text in general, 3 number in chart, 4 number in general (CharXiv constants)
    t = "number" if row.get("reasoning_a_type") in (3, 4) else "exact"
    return ({"question": row["reasoning_q"], "answer_type": t, "answer": row["reasoning_a"]}, _imgs(row, ["image"]))


def chartqa(row, config, split, off):
    # relaxed accuracy, as in ChartQA: numbers within 5%, text exact
    return ({"question": row["query"], "answer_type": "exact", "answer": row["label"], "rel_tol": 0.05,
             "origin": "human" if row.get("human_or_machine") == 0 else "machine"}, _imgs(row, ["image"]))


def docvqa(row, config, split, off):
    if not row.get("answers") or {"figure/diagram", "Image/Photo"} & set(row.get("question_types") or []):
        return None  # a question about a chart or a photo on the page is not reading the document
    return ({"question": row["question"], "answer_type": "anls", "answer": row["answers"],
             "question_types": row.get("question_types")}, _imgs(row, ["image"]))


def ocrbench_kie(row, config, split, off):
    if row.get("question_type") != "Key Information Extraction" or not row.get("answer"):
        return None  # its Doc-oriented VQA is DocVQA, ChartQA and InfoVQA again; the rest is word recognition
    return ({"question": row["question"], "answer_type": "anls", "answer": row["answer"], "subset": row.get("dataset")},
            _imgs(row, ["image"]))


def screenspot_v2(row, config, split, off):
    if row.get("data_type") != "icon":
        return None
    x, y, w, h = row["bbox"]  # pixels, x y width height
    return ({"question": f"This is a screenshot. Where would you click to: {row['instruction']}", "answer_type": "point_in_box",
             "box": [x, y, x + w, y + h], "size": [row["image"]["width"], row["image"]["height"]],
             "platform": row.get("data_source"), "ui_type": row.get("data_type")}, _imgs(row, ["image"]))


def _sspro_rows(part):
    files = json.loads(_get(f"{HUB}/api/datasets/likaixin/ScreenSpot-Pro/tree/main/annotations"))
    out = []
    for f in sorted(x["path"] for x in files if x["path"].endswith(".json")):
        out += json.loads(_get(_hub("likaixin/ScreenSpot-Pro", f)))
    return out


def screenspot_pro(row, config, split, off):
    if row.get("ui_type") != "icon":
        return None
    return ({"question": f"This is a screenshot of {row['application'].replace('_', ' ')}. Where would you click to: "
                         f"{row['instruction']}", "answer_type": "point_in_box", "box": row["bbox"], "size": row["img_size"],
             "group": row.get("group"), "ui_type": row.get("ui_type")},
            [("image", _hub("likaixin/ScreenSpot-Pro", "images/" + row["img_filename"]))])


def mindcube(row, config, split, off):
    n = len(set(re.findall(r"(?:^|\s)([A-E])\.\s", row["question"])))
    if n < 2 or not row.get("gt_answer"):
        return None
    return ({"question": row["question"], "options": None, "n_options": n, "answer_type": "mcq", "answer": row["gt_answer"],
             "setting": (row.get("id") or "").split("_")[0]}, [("image", x["src"]) for x in row["images"]])


def _timeblind_rows(part):
    rows = [json.loads(x) for x in _get(_hub("BaiqiL/TimeBlind", "data.jsonl")).decode().splitlines() if x.strip()]
    return [r for r in rows if r["type"] == part[1]]


def timeblind(row, config, split, off):
    path = row["video_path"].split("/", 1)[1]  # "TimeBlind/videos/x.mp4" -> "videos/x.mp4"
    if row["type"] == "yes_no":
        return ({"question": row["question"], "answer_type": "yesno", "answer": row["answer"]}, [("video", _hub("BaiqiL/TimeBlind", path))])
    return ({"question": row["question"], "options": None, "n_options": 2, "answer_type": "mcq", "answer": row["answer"]},
            [("video", _hub("BaiqiL/TimeBlind", path))])


def _get(url):
    import mm_build  # the HTTP helper (with HF_TOKEN), imported late to avoid a cycle
    return mm_build.get(url, binary=True)


BLINK_PERCEPTION = ("Art_Style", "Counting", "Forensic_Detection", "Functional_Correspondence", "Jigsaw",
                    "Relative_Reflectance", "Semantic_Correspondence", "Visual_Correspondence", "Visual_Similarity")
BLINK_SPATIAL = ("Multi-view_Reasoning", "Object_Localization", "Relative_Depth", "Spatial_Relation")

SOURCES = [
    {"name": "mmmu_pro", "hf": "MMMU/MMMU_Pro", "cap": "reasoning", "tier": "L2", "n": 50,
     "parts": [("standard (10 options)", "test")], "adapt": mmmu_pro, "stratum": lambda it: it["tier"], "license": "apache-2.0",
     "note": "tier from topic_difficulty (Easy L1 / Medium L2 / Hard L3); no tables, charts or screenshots"},
    {"name": "blink", "hf": "BLINK-Benchmark/BLINK", "cap": "perception", "tier": "L2", "n": 54,
     "parts": [(c, "val") for c in BLINK_PERCEPTION], "adapt": blink, "license": "apache-2.0",
     "note": "val split (test answers hidden); 6 per low-level subtask"},
    {"name": "chartqa", "hf": "HuggingFaceM4/ChartQA", "cap": "charts", "tier": "L1", "n": 15, "parts": [("default", "test")],
     "adapt": chartqa, "license": "gpl-3.0", "note": "relaxed accuracy (numbers within 5%)"},
    {"name": "charxiv", "hf": "princeton-nlp/CharXiv", "cap": "charts", "tier": "L3", "n": 35, "parts": [("default", "validation")],
     "adapt": charxiv, "license": "cc-by-sa-4.0", "note": "reasoning questions; exact / numeric match instead of the official GPT grader"},
    {"name": "docvqa", "hf": "lmms-lab-encoder/DocVQA", "cap": "documents", "tier": "L1", "n": 30, "parts": [("DocVQA", "validation")],
     "adapt": docvqa, "license": "apache-2.0 (mirror)", "note": "ANLS; no questions about figures or photos"},
    {"name": "ocrbench_kie", "hf": "echo840/OCRBench", "cap": "documents", "tier": "L2", "n": 20, "parts": [("default", "test")],
     "adapt": ocrbench_kie, "stratum": lambda it: it["subset"], "license": "see dataset card (none stated)",
     "note": "key information extraction from receipts, labels and forms (SROIE, POIE, FUNSD); ANLS"},
    {"name": "cvbench_3d", "hf": "nyu-visionx/CV-Bench", "cap": "spatial", "tier": "L1", "n": 14, "parts": [("3D", "test")],
     "adapt": cvbench, "stratum": lambda it: it["subtask"], "license": "apache-2.0", "note": "depth order and distance"},
    {"name": "blink_spatial", "hf": "BLINK-Benchmark/BLINK", "cap": "spatial", "tier": "L2", "n": 16,
     "parts": [(c, "val") for c in BLINK_SPATIAL], "adapt": blink, "license": "apache-2.0",
     "note": "val split; 4 per spatial subtask"},
    {"name": "mindcube", "hf": "oscarqjh/MindCube_lmmseval", "cap": "spatial", "tier": "L3", "n": 20, "parts": [("tiny", "combined")],
     "adapt": mindcube, "license": "MIT (MLL-Lab/MindCube)", "note": "tinybench, lmms-eval mirror of MLL-Lab/MindCube"},
    {"name": "screenspot_v2", "hf": "lmms-lab/ScreenSpot-v2", "cap": "gui", "tier": "L1", "n": 20, "parts": [("default", "train")],
     "adapt": screenspot_v2, "license": "apache-2.0", "note": "icon targets; the whole benchmark (the mirror calls it train)"},
    {"name": "screenspot_pro", "hf": "likaixin/ScreenSpot-Pro", "cap": "gui", "tier": "L3", "n": 30, "parts": [("annotations", "all")],
     "rows": _sspro_rows, "adapt": screenspot_pro, "license": "MIT", "note": "icon targets in high-resolution professional software"},
    {"name": "timeblind", "hf": "BaiqiL/TimeBlind", "cap": "video", "tier": "L3", "n": 50,
     "parts": [("data", "yes_no"), ("data", "multiple_choice")], "rows": _timeblind_rows, "adapt": timeblind, "needs": ["ffmpeg"],
     "license": "research use (dataset card)", "note": "temporal minimal pairs, scored per question"},
]
