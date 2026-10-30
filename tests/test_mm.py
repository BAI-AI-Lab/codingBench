"""Multimodal ladder (cb mm) on synthetic items (no downloads): answer extraction and scoring for every answer type,
then generation against tests/mock_openai.py for two mock models and the report.

  python tests/test_mm.py          # the end-to-end part needs openai + httpx; the figure part needs matplotlib
"""
import importlib.util
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CB = tempfile.mkdtemp(prefix="cb_mm_test_")
os.environ["CB"] = CB
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mm_lib as M  # noqa: E402


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def png(w=8, h=6, rgb=(200, 30, 30)):
    """A tiny solid-colour PNG, without PIL."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def item(iid, cap, tier, source, question, answer_type, answer, frames=0, **extra):
    d = M.item_dir(iid)
    os.makedirs(d, exist_ok=True)
    names = []
    for i in range(max(frames, 1)):
        names.append(f"{'frame' if frames else 'img'}{i}.png")
        open(os.path.join(d, names[-1]), "wb").write(png(rgb=(10 * i, 100, 200)))
    it = {"id": iid, "source": source, "capability": cap, "tier": tier, "question": question, "answer_type": answer_type,
          "answer": answer, "images": [] if frames else names, "frames": names if frames else []}
    it.update(extra)
    json.dump(it, open(os.path.join(d, "item.json"), "w"))
    return it


def units():
    f = M.final_answer
    check(f("Let me think.\n**Answer:** B") == "B" and f("答案：42。") == "42" and f("so \\boxed{7}") == "so 7" and f("") is None,
          "final answer: Answer:, 答案：, \\boxed, empty")
    check(f("Answer: A\nWait, re-check.\nFinal answer: C") == "C", "final answer: the last Answer: line counts")
    check(M.parse_letter("(B) the cat", 4) == "B" and M.parse_letter("Option D", 4) == "D" and M.parse_letter("E", 4) is None
          and M.parse_letter("A or B", 4) is None, "option letters: (B), Option D; out of range or ambiguous -> none")
    mcq = {"answer_type": "mcq", "options": ["x", "y", "z"], "answer": "C"}
    check(M.score(mcq, "...\nAnswer: C") == (1.0, "C") and M.score(mcq, "Answer: B")[0] == 0
          and M.score(mcq, "no idea")[1] is None, "mcq: right, wrong, unreadable")
    num = {"answer_type": "number", "answer": "3200"}
    check(M.score(num, "Answer: 3,200")[0] == 1 and M.score(num, "Answer: 3215")[0] == 1 and M.score(num, "Answer: 3300")[0] == 0,
          "number: commas, 1% tolerance")
    rng = {"answer_type": "number", "answer": "5", "range": [4.5, 5.5]}
    check(M.score(rng, "Answer: 5.4")[0] == 1 and M.score(rng, "Answer: 5.6")[0] == 0, "number: accepted range")
    ex = {"answer_type": "exact", "answer": ["The Blue Line", "blue"]}
    check(M.score(ex, "Answer: blue line")[0] == 1 and M.score(ex, "Answer: Blue.")[0] == 1 and M.score(ex, "Answer: red")[0] == 0,
          "exact: normalised text, any gold")
    yn = {"answer_type": "yesno", "answer": "Yes"}
    check(M.score(yn, "Answer: yes")[0] == 1 and M.score(yn, "Answer: No")[0] == 0, "yes/no")
    an = {"answer_type": "anls", "answer": ["$1,250.00"]}
    check(M.score(an, "Answer: $1,250.00")[0] == 1 and 0.8 < M.score(an, "Answer: $1,250.0")[0] < 1
          and M.score(an, "Answer: nothing")[0] == 0, "anls: exact 1, near miss partial, far 0")
    pt = {"answer_type": "point_in_box", "size": [2000, 1000], "box": [100, 100, 300, 200]}
    check(M.score(pt, "Answer: (100, 150)")[0] == 1 and M.score(pt, "Answer: (0.1, 0.15)")[0] == 1
          and M.score(pt, "Answer: (500, 500)")[0] == 0 and M.score(pt, "click there")[1] is None,
          "point: 0-1000 and fractional coordinates, outside the box, unreadable")
    mask = {"answer_type": "point_in_mask", "size": [10, 10], "mask": {"3": [[2, 5]]}}
    check(M.score(mask, "Answer: (300, 350)")[0] == 1 and M.score(mask, "Answer: (600, 350)")[0] == 0
          and M.score(mask, "Answer: (300, 450)")[0] == 0, "point in mask: inside a run, beside it, another row")
    emb = {"answer_type": "mcq", "options": None, "n_options": 2, "answer": "B"}
    check(M.score(emb, "Answer: B")[0] == 1 and M.score(emb, "Answer: C")[1] is None and "A." not in M.prompt_text(
        {"question": "Q? A. x B. y", "options": None, "answer_type": "mcq"}).split("\n\n")[-1],
        "mcq with the options inside the question: letters limited, none added")
    import mm_build as Bd
    src = {"name": "fake", "hf": "x/y", "cap": "reasoning", "tier": "L2", "n": 6, "parts": [("a", "s")],
           "rows": lambda part: [{"q": f"q{i}", "t": "L1" if i % 3 == 0 else "L2", "img": png()} for i in range(30)],
           "adapt": lambda r, c, s, o: ({"question": r["q"], "options": ["x", "y"], "answer_type": "mcq", "answer": "A",
                                         "tier": r["t"]}, [("image", r["img"])]),
           "stratum": lambda it: it["tier"]}
    ids = Bd.build(src, 0, False)
    check(len(ids) == 6 and Bd.build(src, 0, False) == ids and Bd.build(src, 1, False) != ids
          and sum(M.load_item(i)["tier"] == "L1" for i in ids) == 3 and M.load_item(ids[0])["images"] == ["img0.png"],
          "build: same seed same items, strata in turn, images written")
    real_get = Bd.get
    Bd.get = lambda url, binary=False: ({"rows": [{"row_idx": 0, "row": {}}]} if "/rows?" in url else
                                        {"size": {"splits": [{"dataset": "a/b", "config": "default", "split": "test"}]}})
    stale = []
    for f in (lambda: Bd.rows("x/y", "c", "s", 5), lambda: Bd.num_rows("x/y", "c", "s")):
        try:
            f()
        except RuntimeError:
            stale.append(True)
    Bd.get = real_get
    check(stale == [True, True], "datasets-server answers for other rows or another dataset (a caching proxy) stop the build")
    it = item("unit/a/1", "reasoning", "L1", "unit", "What colour?", "mcq", "A", options=["red", "blue"])
    msgs, logged = M.messages(it, "high")
    sent = json.dumps(msgs)
    check("data:image/png;base64," in sent and '"detail": "high"' in sent and "base64" not in json.dumps(logged)
          and logged[0]["content"][-1]["text"].endswith('"Answer: X".'), "messages: image as data URL, logs keep file names")
    v = item("unit/v/1", "video", "L2", "unit", "What happens?", "mcq", "B", frames=3, options=["x", "y"])
    msgs, _ = M.messages(v)
    check(len([p for p in msgs[0]["content"] if p["type"] == "image_url"]) == 3 and "3 images are frames" in msgs[0]["content"][0]["text"],
          "video: frames in order, introduced as frames")
    shutil.rmtree(M.ITEMS)


def fixture():
    ids = {c: [] for c in ("reasoning", "documents", "spatial", "gui", "video")}
    for i in range(4):
        ids["spatial"].append(item(f"fake_ref/loc/{i}", "spatial", "L3", "fake_ref", f"Point to the cup {i}.", "point_in_mask", None,
                                   size=[8, 6], mask={str(i + 1): [[1, 4]]})["id"])
    for i in range(8):
        ids["reasoning"].append(item(f"fake_mmmu/std/{i}", "reasoning", "L1" if i < 4 else "L3", "fake_mmmu",
                                     f"Question {i}: which option is right?", "mcq", "ABCD"[i % 4], options=list("wxyz"))["id"])
        ids["documents"].append(item(f"fake_docvqa/val/{i}", "documents", "L1", "fake_docvqa", f"What is total {i}?", "anls",
                                     [f"{i * 100} dollars"])["id"])
    for i in range(6):
        ids["gui"].append(item(f"fake_ss/pro/{i}", "gui", "L3", "fake_ss", f"Click the save button {i}", "point_in_box", None,
                               size=[1920, 1080], box=[100 * i, 50, 100 * i + 80, 90])["id"])
        ids["video"].append(item(f"fake_tomato/t/{i}", "video", "L3", "fake_tomato", f"Does the ball move left {i}?", "yesno",
                                 "yes" if i % 2 else "no", frames=4)["id"])
    os.makedirs(M.DATA, exist_ok=True)
    man = os.path.join(M.DATA, "mm.json")
    json.dump({"version": "test", "capabilities": ids}, open(man, "w"))
    return man, ids


def main():
    units()
    man, ids = fixture()
    try:
        import httpx  # noqa: F401
        import openai  # noqa: F401
    except ImportError:
        print("skip end-to-end part: openai not installed")
        return
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "mock_openai.py"), "--port", str(port)],
                            env=dict(os.environ), stdout=subprocess.PIPE, text=True)
    try:
        mock.stdout.readline()
        runs = {}
        for model in ("mock", "mock-weak"):
            runs[model] = os.path.join(CB, "runs", model, "mm-full")
            env = dict(os.environ, MODEL=model, OPENAI_BASE_URL=f"http://127.0.0.1:{port}/v1", OPENAI_API_KEY="x",
                       WORKERS="4", REASONING_EFFORT="low")
            subprocess.run([sys.executable, os.path.join(ROOT, "bin", "mm_run.py"), "--out", runs[model], "--manifest", man,
                            "--k", "2"], env=env, check=True)
        run = runs["mock"]
        n = sum(len(v) for v in ids.values())
        answers = [json.loads(x) for x in open(os.path.join(run, "answers.jsonl"))]
        check(len(answers) == 2 * n and all(a["text"] for a in answers), f"mm_run: {2 * n} samples answered")
        usage = open(os.path.join(run, "usage.jsonl")).read()
        check("base64" not in usage and "file:img0.png" in usage, "usage log: images by file name, no base64")
        info = json.load(open(os.path.join(run, "run.json")))
        check(info["reasoning_effort"] == "low" and "temperature" in info["omit"], "run.json: reasoning effort, temperature left out")
        before = len(usage.splitlines())
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "mm_run.py"), "--out", run, "--manifest", man, "--k", "2"],
                       env=dict(env, MODEL="mock"), check=True)
        check(len(open(os.path.join(run, "usage.jsonl")).read().splitlines()) == before, "re-run asks nothing again")
        smoke = os.path.join(CB, "runs", "mock", "mm-smoke")
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "mm_run.py"), "--out", smoke, "--manifest", man, "--smoke"],
                       env=dict(env, MODEL="mock"), check=True)
        check(len(open(os.path.join(smoke, "answers.jsonl")).read().splitlines()) == len(ids), "smoke: one item per capability")
        out = os.path.join(CB, "report")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mm_report.py"), runs["mock"], runs["mock-weak"], "--out", out,
                        "--prices", "mock=1,0.1,2;mock-weak=0.5,0.05,1", "--intro", ""], check=True)
        rep = json.load(open(os.path.join(out, "report.json")))
        p = rep["profile"]
        check(p["n"] == n and p["overall"][0] == 100 and 0 < p["overall"][1] < 100, "report: mock scores 100, the weak mock less")
        check(p["rank"] == [1, 2] and p["pairs"]["0,1"]["ci"][0] > 0 and p["pairs"]["0,1"]["wins"] > 0
              and p["pairs"]["0,1"]["losses"] == 0, "ranking: the paired interval puts mock first")
        check(abs(p["overall"][1] - sum(p["cap"][1].values()) / len(p["caps"])) < 1e-9, "overall = equal-weight mean of capabilities")
        md = open(os.path.join(out, "report.md")).read()
        check(all(x in md for x in ("## 总结", "## 能力画像", "## 排名", "## 按难度", "## 按来源", "## 成本与速度", "第 1 名 mock",
                                    "视频理解", "由 Albert Huang 创建于")) and "base64" not in md, "report.md: every section, no images")
        tex = open(os.path.join(out, "main.tex")).read()
        check(r"\section{排名}" in tex and "多模态阶梯评测" in tex, "main.tex written")
        out2 = os.path.join(CB, "report2")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mm_report.py"), "--from-json", os.path.join(out, "report.json"),
                        "--out", out2, "--intro", ""], check=True)
        check(open(os.path.join(out2, "report.md")).read() == md, "--from-json renders the same report")
        if importlib.util.find_spec("matplotlib"):
            check(os.path.exists(os.path.join(out, "fig_profile.pdf")) and "fig_profile.png" in md, "profile chart drawn")
        one = os.path.join(CB, "report1")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mm_report.py"), runs["mock-weak"], "--out", one, "--intro", ""],
                       check=True)
        check("第 1 名 mock-weak" in open(os.path.join(one, "report.md")).read(), "a single run gets a profile too")
    finally:
        mock.terminate()
    shutil.rmtree(CB, ignore_errors=True)
    print("all mm tests passed")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"{time.time() - t0:.1f} s")
