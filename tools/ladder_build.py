"""Build the ladder test set from the downloaded sources (tools/ladder_download.sh) into $CB/data/ladder/problems/.

  python ladder_build.py [--sources usaco,egoi2026,ioi2026,frontiercs] [--only <pid>,...]
  python ladder_build.py --calibrate [--only ...] [--workers 32]   # judge the official solutions on every test
  python ladder_build.py --manifest samples/ladder.json            # write the frozen problem list (metadata only)

Tiers: USACO Bronze -> L1, Silver -> L2 (answered in Python), Gold -> L3, Platinum -> L4 (C++); EGOI 2026 joins L3 and
IOI 2026 joins L4 (the "2026" subset, newer than the USACO problems); FrontierCS algorithmic problems are L5.
Statements stay on the server: the manifest in the repo holds ids, tiers, dates and limits only.
"""
import argparse
import concurrent.futures
import glob
import html
import json
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder_lib as L  # noqa: E402

TIER_OF_DIVISION = {"bronze": "L1", "silver": "L2", "gold": "L3", "platinum": "L4"}
# contest page -> (season, month the contest started); USACO pages give no exact dates for 2024-25
CONTESTS = {"dec24results": ("2024-25", "2024-12"), "jan25results": ("2024-25", "2025-01"),
            "feb25results": ("2024-25", "2025-02"), "open25results": ("2024-25", "2025-03"),
            "season26contest1results": ("2025-26", "2026-01"), "season26contest2results": ("2025-26", "2026-01"),
            "season26contest3results": ("2025-26", "2026-02")}
MULTI_ANSWER = re.compile(r"(?i)(if there are (multiple|many|several)[^.]{0,80}(any|one)\b|output any|print any|any (valid|such) "
                          r"(answer|solution|sequence|assignment|construction|arrangement)|any of them)")


def resolve_link(path):
    """A git symlink downloaded file by file (raw.githubusercontent.com) arrives as a one-line file holding the
    relative target, e.g. "../../../common/checker.cpp" (EGOI 2026 does this for shared checkers): follow it."""
    for _ in range(5):
        if os.path.getsize(path) > 512:
            return path
        text = open(path, errors="replace").read().strip()
        if "\n" in text or not re.fullmatch(r"[\w./-]+", text):
            return path
        target = os.path.normpath(os.path.join(os.path.dirname(path), text))
        if not os.path.isfile(target) or target == path:
            return path
        path = target
    return path


def copy_resolved(src, dst):
    shutil.copy(resolve_link(src), dst)


def write_problem(pid, meta, statement, tests_src=None):
    d = os.path.join(L.PROBLEMS, pid)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "statement.md"), "w").write(statement.strip() + "\n")
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1, ensure_ascii=False)
    return d


# ---------------------------------------------------------------- USACO

def usaco_text(h):
    """The statement part of a USACO problem page as Markdown-ish text; $...$ math is kept as in the page."""
    m = re.search(r'<span id="probtext-text"[^>]*>(.*?)(?:Problem credits:|</span>\s*</div>)', h, re.S)
    body = m.group(1) if m else h

    def pre(m):
        return "\n```\n" + html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip("\n") + "\n```\n"
    body = re.sub(r"(?is)<pre( class='(?:in|out)')?>(.*?)</pre>", pre, body)
    body = re.sub(r"(?is)<h4>(.*?)</h4>", lambda m: "\n\n" + m.group(1).strip() + "\n", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</?p>|</?div[^>]*>", "\n\n", body)
    body = re.sub(r"(?i)<li>", "\n- ", body)
    body = re.sub(r"(?i)</?(strong|b)>", "**", body).replace("****", "**")
    body = re.sub(r"(?i)</?(em|i)>", "*", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    body = re.sub(r"[ \t]+\n", "\n", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def usaco_codes(h):
    """Complete programs in a USACO solution page: [(lang, code)], C++ and Python only."""
    out = []
    for raw in re.findall(r"(?is)<pre[^>]*>(.*?)</pre>", h):
        code = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip("\n") + "\n"
        if "#include" in code and re.search(r"\bmain\s*\(", code):
            out.append(("cpp", code))
        elif "public class" not in code and "#include" not in code and re.search(r"input\(|sys\.stdin|open\(0\)", code):
            out.append(("python", code))
    return out


def build_usaco(only=None):
    index = []  # (contest page, cpid, test-data zip, solution page) from the downloaded results pages
    for page in CONTESTS:
        f = os.path.join(L.RAW, "usaco", "pages", f"{page}.html")
        if os.path.exists(f):
            index += [(page, *m.groups()) for m in re.finditer(
                r"cpid=(\d+)'>View problem</a>.*?href='(current/data/[^']+\.zip)'.*?href='(current/data/sol_[^']+\.html)'",
                open(f, errors="replace").read(), re.S)]
    n = 0
    for page, cpid, z, sol in index:
        pid = f"usaco-{cpid}"
        if only and pid not in only:
            continue
        raw = os.path.join(L.RAW, "usaco", cpid)
        if not os.path.exists(os.path.join(raw, "tests.zip")):
            print(f"skip {pid}: not downloaded yet")
            continue
        div = re.search(r"_(bronze|silver|gold|platinum)_", z).group(1)
        num = int(re.search(r"prob(\d)_", z).group(1))
        tier = TIER_OF_DIVISION[div]
        lang = L.LANG[tier]
        h = open(os.path.join(raw, "problem.html"), errors="replace").read()
        title = re.search(r"<h2>\s*Problem \d\.\s*(.*?)\s*</h2>", h, re.S)
        contest = re.search(r"<h2>\s*(USACO [^<]*?)\s*</h2>", h)
        text = usaco_text(h)
        tl_cpp = float((re.search(r"(?i)time limit for this problem is\s*(\d+(?:\.\d+)?)\s*s", text) or [0, 2])[1])
        ml = int((re.search(r"(?i)memory limit for this problem is\s*(\d+)\s*MB", text) or [0, 256])[1])
        d = os.path.join(L.PROBLEMS, pid)
        tdir = os.path.join(d, "tests")
        shutil.rmtree(tdir, ignore_errors=True)
        os.makedirs(tdir)
        tests = []
        with zipfile.ZipFile(os.path.join(raw, "tests.zip")) as zf:
            names = [x for x in zf.namelist() if not x.endswith("/") and "__MACOSX" not in x]
            pairs = {}
            for x in names:
                b = os.path.basename(x)
                m = re.fullmatch(r"(\d+)\.(in|out)", b) or re.fullmatch(r"([IO])\.(\d+)", b)
                if not m:
                    continue
                k, kind = (m.group(1), m.group(2)) if m.group(2) in ("in", "out") else (m.group(2), "in" if m.group(1) == "I" else "out")
                pairs.setdefault(int(k), {})[kind] = x
            for k in sorted(pairs):
                if set(pairs[k]) != {"in", "out"}:
                    continue
                for kind in ("in", "out"):
                    with zf.open(pairs[k][kind]) as src, open(os.path.join(tdir, f"{k}.{kind}"), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                tests.append({"name": str(k), "in": f"{k}.in", "out": f"{k}.out"})
        codes = usaco_codes(open(os.path.join(raw, "solution.html"), errors="replace").read())
        rdir = os.path.join(d, "ref")
        shutil.rmtree(rdir, ignore_errors=True)
        os.makedirs(rdir)
        cands = []
        for i, (cl, code) in enumerate(codes):
            f = f"cand{i}.{'cpp' if cl == 'cpp' else 'py'}"
            open(os.path.join(rdir, f), "w").write(code)
            cands.append({"file": f, "lang": cl})
        season, month = CONTESTS[page]
        multi = bool(MULTI_ANSWER.search(text))
        meta = {"pid": pid, "source": "usaco", "subset": f"USACO {season}", "tier": tier, "lang": lang,
                "title": html.unescape(title.group(1)).strip() if title else pid,
                "contest": contest.group(1).strip() if contest else page, "division": div, "number": num,
                "date": month, "url": f"https://usaco.org/index.php?page=viewproblem2&cpid={cpid}",
                "tl": tl_cpp * (2 if lang == "python" else 1), "tl_cpp": tl_cpp, "ml": ml,
                "judge": {"kind": "tokens"}, "scoring": {"type": "tests"}, "tests": tests, "ref_candidates": cands,
                "multi_answer": multi}
        write_problem(pid, meta, text)
        n += 1
        print(f"{pid} {tier} {meta['title']}: {len(tests)} tests, {len(cands)} reference candidates"
              + (", MAY NEED A CHECKER (multiple answers)" if multi else ""))
    return n


# ---------------------------------------------------------------- EGOI 2026 (CMS / task-maker format)

def toml_load(path):
    import tomllib
    return tomllib.load(open(path, "rb"))


def typst_to_text(src, consts, subtasks, samples, scores):
    """EGOI's Typst statement -> Markdown-ish text: constraint.X / subtask.X filled in from gen.toml, the
    #examples() call replaced by the sample files, #subtasks((...)) by a numbered list with the points."""
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    s = re.sub(r"(?m)^#(import|set|show)\b.*$", "", s)
    s = re.sub(r"constraint\.([A-Za-z0-9_]+)", lambda m: str(consts.get(m.group(1), m.group(0))), s)
    m = re.search(r"#subtasks\(\((.*?)\)\)\s*$", s, re.S | re.M)
    if m:
        items = re.findall(r"subtask\s*=>\s*\[(.*?)\]\s*,?\s*(?=subtask\s*=>|$)", m.group(1), re.S)
        lines = []
        for i, it in enumerate(items):
            vals = subtasks[i] if i < len(subtasks) else {}
            it = re.sub(r"subtask\.([A-Za-z0-9_]+)", lambda x: str(vals.get(x.group(1), consts.get(x.group(1), x.group(0)))), it)
            pts = scores[i] if i < len(scores) else "?"
            lines.append(f"{i + 1}. ({pts:g} points) {' '.join(it.split())}" if isinstance(pts, (int, float)) else f"{i + 1}. {' '.join(it.split())}")
        s = s[:m.start()] + "\n".join(lines) + "\n" + s[m.end():]
    ex = "\n".join(f"Sample input {i + 1}:\n```\n{a.strip()}\n```\nSample output {i + 1}:\n```\n{b.strip()}\n```\n"
                   for i, (a, b) in enumerate(samples))
    s = re.sub(r"#examples\(\)", "== Examples\n\n" + ex, s)
    s = re.sub(r"#statement\(title:\s*\"([^\"]*)\"\)\[", r"# \1\n", s)
    s = re.sub(r"(?m)^#(constraints|scoring|explanation)\s*$", lambda m: "== " + m.group(1).capitalize(), s)
    s = re.sub(r"(?m)^(=+) ", lambda m: "#" * (len(m.group(1)) + 1) + " ", s)
    s = re.sub(r"(?m)^\]\s*$", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def build_egoi(only=None):
    root = os.path.join(L.RAW, "egoi2026")
    n = 0
    for tdir in sorted(glob.glob(os.path.join(root, "day*", "*"))):
        if not os.path.isfile(os.path.join(tdir, "task.yaml")):
            continue
        name = os.path.basename(tdir)
        pid = f"egoi26-{name}"
        if only and pid not in only:
            continue
        cfg = toml_load(os.path.join(tdir, "task.toml"))
        yml = yaml_load(os.path.join(tdir, "task.yaml"))
        gen = toml_load(os.path.join(tdir, "gen", "gen.toml")) if os.path.exists(os.path.join(tdir, "gen", "gen.toml")) else {}
        consts = {k: v for k, v in gen.items() if not isinstance(v, dict)}
        subt = [dict(consts, **v) for v in (gen.get("subtask") or {}).values()]
        groups = [{"max_score": float(g["max_score"]), "tests": [str(int(t)) for t in g["testcases"]]}
                  for g in yml["score_type_parameters"]]
        d = os.path.join(L.PROBLEMS, pid)
        os.makedirs(os.path.join(d, "tests"), exist_ok=True)
        tests = []
        for f in sorted(glob.glob(os.path.join(tdir, "input", "input*.txt")), key=lambda p: int(re.findall(r"\d+", os.path.basename(p))[0])):
            k = re.findall(r"\d+", os.path.basename(f))[0]
            o = os.path.join(tdir, "output", f"output{k}.txt")
            if not os.path.exists(o):
                continue
            shutil.copy(f, os.path.join(d, "tests", f"{k}.in"))
            shutil.copy(o, os.path.join(d, "tests", f"{k}.out"))
            tests.append({"name": str(int(k)), "in": f"{k}.in", "out": f"{k}.out"})
        sdir = os.path.join(tdir, "statement")
        samples = []
        sample_dir = sdir if glob.glob(os.path.join(sdir, f"{name}.input*.txt")) else os.path.join(tdir, "att")
        for f in sorted(glob.glob(os.path.join(sample_dir, f"{name}.input*.txt")), key=lambda p: int(re.findall(r"input(\d+)", p)[0])):
            o = f.replace(".input", ".output")
            if os.path.exists(o):
                samples.append((open(f).read(), open(o).read()))
        typ = open(os.path.join(sdir, "english.typ")).read()
        text = typst_to_text(typ, consts, subt, samples, [g["max_score"] for g in groups])
        title = (re.search(r"^# (.*)$", text, re.M) or [0, name])[1]
        chk = os.path.join(tdir, "check", "checker.cpp")
        judge = {"kind": "tokens"}
        if any(os.path.exists(os.path.join(tdir, "check", f)) for f in ("manager", "manager.cpp", "controller", "controller.cpp")):
            # interactive: a CMS manager (seatingplan) or EGOI's controller that runs the contestant as several
            # processes (census); their expected outputs are empty, so token comparison would fail every answer
            judge = {"kind": "communication", "task_type": "Communication"}
        elif os.path.exists(chk):
            cdir = os.path.join(d, "checker")
            os.makedirs(cdir, exist_ok=True)
            copy_resolved(chk, os.path.join(cdir, "checker.cpp"))
            for h in glob.glob(os.path.join(tdir, "check", "*.h")) + glob.glob(os.path.join(root, "common", "*.h")):
                copy_resolved(h, os.path.join(cdir, os.path.basename(h)))
            judge = {"kind": "checker", "convention": "cms", "source": "checker/checker.cpp"}
        refs = []
        os.makedirs(os.path.join(d, "ref"), exist_ok=True)
        for f in sorted(glob.glob(os.path.join(tdir, "sol", "*.cpp")) + glob.glob(os.path.join(tdir, "solution", "*.cpp"))):
            shutil.copy(f, os.path.join(d, "ref", os.path.basename(f)))
            refs.append({"file": os.path.basename(f), "lang": "cpp"})
        meta = {"pid": pid, "source": "egoi2026", "subset": "2026", "tier": "L3", "lang": "cpp", "title": title,
                "contest": "EGOI 2026", "date": "2026-05", "url": "https://github.com/egoi-org/egoi-2026",
                "tl": float(cfg["time_limit"]), "ml": int(cfg["memory_limit"]), "judge": judge,
                "scoring": {"type": "groupmin", "groups": groups}, "tests": tests, "ref_candidates": refs}
        write_problem(pid, meta, text)
        n += 1
        print(f"{pid} L3 {title}: {len(tests)} tests, {len(groups)} subtasks, {len(refs)} reference candidates")
    return n


def yaml_load(path):
    """task.yaml of task-maker: the few keys we need (name, title, score_type_parameters) without PyYAML."""
    try:
        import yaml
        return yaml.safe_load(open(path))
    except ImportError:
        pass
    groups, cur = [], None
    for line in open(path):
        m = re.match(r"^- max_score:\s*([\d.]+)", line)
        if m:
            cur = {"max_score": float(m.group(1)), "testcases": []}
            groups.append(cur)
            continue
        m = re.match(r"^\s+- '?([0-9]+)'?\s*$", line)
        if m and cur is not None:
            cur["testcases"].append(m.group(1))
    return {"score_type_parameters": groups}


# ---------------------------------------------------------------- IOI 2026 (TPS format)

def build_ioi(only=None):
    root = os.path.join(L.RAW, "ioi2026")
    n = 0
    for tdir in sorted(glob.glob(os.path.join(root, "day*", "*"))):
        pj = os.path.join(tdir, "problem.json")
        if not os.path.exists(pj):
            continue
        prob = json.load(open(pj))
        name = prob["code"]
        pid = f"ioi26-{name}"
        if only and pid not in only:
            continue
        ttype = prob["task_type"]
        nproc = prob["task_type_params"][0] if ttype == "Communication" else 1
        d = os.path.join(L.PROBLEMS, pid)
        os.makedirs(os.path.join(d, "tests"), exist_ok=True)
        tests = []
        for f in sorted(glob.glob(os.path.join(tdir, "tests", "*.in"))):
            k = os.path.basename(f)[:-3]
            o = f[:-3] + ".out"
            shutil.copy(f, os.path.join(d, "tests", f"{k}.in"))
            if os.path.exists(o):
                shutil.copy(o, os.path.join(d, "tests", f"{k}.out"))
            tests.append({"name": k, "in": f"{k}.in", "out": f"{k}.out" if os.path.exists(o) else None})
        groups = []
        for f in sorted(glob.glob(os.path.join(tdir, "subtasks", "*.json"))):
            s = json.load(open(f))
            groups.append({"max_score": float(s["score"]), "tests": s["testcases"], "name": os.path.basename(f)[:-5]})
        gdir = os.path.join(d, "checker")
        shutil.rmtree(gdir, ignore_errors=True)
        shutil.copytree(os.path.join(tdir, "graders"), gdir, ignore=shutil.ignore_patterns(".DS_Store", "manager"))
        for f in glob.glob(os.path.join(gdir, "*")):
            r = resolve_link(f)
            if r != f:
                shutil.copy(r, f)
        for f in glob.glob(os.path.join(tdir, "checker", "*")):
            copy_resolved(f, os.path.join(gdir, os.path.basename(f)))
        header = [os.path.basename(h) for h in glob.glob(os.path.join(gdir, "*.h")) if os.path.basename(h) != "testlib.h"]
        judge = {"kind": "grader" if ttype in ("Batch", "BatchAndOutput") else "communication", "task_type": ttype,
                 "processes": nproc, "header": header[0] if header else f"{name}.h",
                 "grader": "grader.cpp" if os.path.exists(os.path.join(gdir, "grader.cpp")) else "stub.cpp",
                 "checker": "checker.cpp" if os.path.exists(os.path.join(gdir, "checker.cpp")) else None,
                 "manager": "manager.cpp" if os.path.exists(os.path.join(gdir, "manager.cpp")) else None}
        refs = []
        os.makedirs(os.path.join(d, "ref"), exist_ok=True)
        for f in sorted(glob.glob(os.path.join(tdir, "solutions", "model_solution", "*.cpp"))
                        + glob.glob(os.path.join(tdir, "solutions", "correct", "*.cpp"))):
            b = os.path.basename(f)
            shutil.copy(f, os.path.join(d, "ref", b))
            refs.append({"file": b, "lang": "cpp"})
        stmt = os.path.join(d, "statement.md")
        text = open(stmt).read() if os.path.exists(stmt) else ""  # written by hand from en.pdf (see below)
        if not text:
            print(f"{pid}: statement.md missing — convert {tdir}/en.pdf first (pdftotext -layout, then clean up)")
        meta = {"pid": pid, "source": "ioi2026", "subset": "2026", "tier": "L4", "lang": "cpp", "title": prob["name"],
                "contest": "IOI 2026", "date": "2026-08", "url": "https://ioi2026.uz/tasks",
                "tl": float(prob["time_limit"]), "ml": int(prob["memory_limit"]) >> 20, "judge": judge,
                "scoring": {"type": "groupmin", "groups": groups}, "tests": tests, "ref_candidates": refs}
        json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1, ensure_ascii=False)
        n += 1
        print(f"{pid} L4 {prob['name']} ({ttype}, {nproc} process(es)): {len(tests)} tests, {len(groups)} subtasks, "
              f"{len(refs)} reference candidates")
    return n


# ---------------------------------------------------------------- FrontierCS algorithmic (L5)

def parse_size(s, unit):
    s = str(s).strip().lower()
    m = re.fullmatch(r"([\d.]+)\s*([a-z]*)", s)
    v, u = float(m.group(1)), m.group(2)
    if unit == "s":
        return v / 1000 if u == "ms" else v
    return int(v * {"g": 1024, "gb": 1024, "m": 1, "mb": 1, "k": 1 / 1024, "kb": 1 / 1024}.get(u, 1 / (1 << 20)))


def build_frontiercs(only=None):
    import yaml  # PyYAML comes with the livecodebench venv (datasets)
    root = os.path.join(L.RAW, "frontiercs", "algorithmic", "problems")
    n = 0
    for pdir in sorted(glob.glob(os.path.join(root, "*")), key=lambda p: int(os.path.basename(p)) if os.path.basename(p).isdigit() else 1 << 30):
        if not os.path.exists(os.path.join(pdir, "config.yaml")):
            continue
        pid = f"fcs-{os.path.basename(pdir)}"
        if only and pid not in only:
            continue
        cfg = yaml.safe_load(open(os.path.join(pdir, "config.yaml")))
        gt = cfg.get("time_limit") or cfg.get("time") or "1s"
        gm = cfg.get("memory_limit") or cfg.get("memory") or "256m"
        isuf, osuf = cfg.get("input_suffix", ".in"), cfg.get("output_suffix", ".ans")
        tdir = os.path.join(pdir, "testdata")
        cases, cur = [], 1
        subtasks = cfg.get("subtasks") or []
        for si, st in enumerate(subtasks):
            t, m = st.get("time_limit") or st.get("time") or gt, st.get("memory_limit") or st.get("memory") or gm
            if "n_cases" in st:
                for i in range(int(st["n_cases"])):
                    cases.append((f"{cur + i}{isuf}", f"{cur + i}{osuf}", t, m))
                cur += int(st["n_cases"])
            else:
                for c in st.get("cases", []):
                    cases.append((c["input"], c["output"], c.get("time") or t, c.get("memory") or m))
        have = {c[0] for c in cases}
        fb = subtasks[-1] if subtasks else {}
        ft, fm = fb.get("time_limit") or fb.get("time") or gt, fb.get("memory_limit") or fb.get("memory") or gm
        for f in sorted(glob.glob(os.path.join(tdir, f"*{isuf}")), key=lambda p: (len(p), p)):
            b = os.path.basename(f)
            if b in have:
                continue
            stem = b[: -len(isuf)]
            o = next((stem + s for s in (".ans", ".out") if os.path.exists(os.path.join(tdir, stem + s))), None)
            if o:
                cases.append((b, o, ft, fm))
        d = os.path.join(L.PROBLEMS, pid)
        os.makedirs(d, exist_ok=True)
        link = os.path.join(d, "tests")
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link) if os.path.islink(link) else shutil.rmtree(link)
        os.symlink(tdir, link)  # 2 GB of tests: link instead of copying
        tests = []
        for i, (inp, out, t, m) in enumerate(cases):
            if not os.path.exists(os.path.join(tdir, inp)):
                continue
            o = out if os.path.exists(os.path.join(tdir, out)) else re.sub(r"\.ans$", ".out", out)
            tests.append({"name": inp[: -len(isuf)], "in": inp, "out": o, "tl": parse_size(t, "s"), "ml": parse_size(m, "mb")})
        kind = cfg.get("type", "default")
        cdir = os.path.join(d, "checker")
        os.makedirs(cdir, exist_ok=True)
        inc = os.path.join(L.RAW, "frontiercs", "algorithmic", "judge", "include")
        for f in glob.glob(os.path.join(inc, "*")):
            shutil.copy(f, cdir)
        chk = cfg.get("checker") or "chk.cc"
        judge = {"kind": "testlib", "checker": chk, "interactor": None}
        if os.path.exists(os.path.join(pdir, chk)):
            shutil.copy(os.path.join(pdir, chk), cdir)
        if kind == "interactive":
            it = cfg.get("interactor") or "interactor.cc"
            shutil.copy(os.path.join(pdir, it), cdir)
            judge["interactor"] = it
        statement = open(os.path.join(pdir, "statement.txt")).read()
        tag = open(os.path.join(pdir, "tag.txt")).read().strip() if os.path.exists(os.path.join(pdir, "tag.txt")) else ""
        meta = {"pid": pid, "source": "frontiercs", "subset": "FrontierCS", "tier": "L5", "lang": "cpp",
                "title": f"FrontierCS #{os.path.basename(pdir)}", "tag": tag, "contest": "FrontierCS algorithmic v1.1",
                "date": "2026-05", "url": f"https://github.com/FrontierCS/Frontier-CS/tree/main/algorithmic/problems/{os.path.basename(pdir)}",
                "tl": max((t["tl"] for t in tests), default=1.0), "ml": max((t["ml"] for t in tests), default=256),
                "judge": judge, "scoring": {"type": "mean"}, "tests": tests, "ref_candidates": [],
                "filename": cfg.get("filename")}
        write_problem(pid, meta, statement)
        n += 1
    print(f"frontiercs: {n} problems")
    return n


# ---------------------------------------------------------------- calibration: official solutions on every test

def checker_selftest(meta, n=3):
    """For problems without official solutions (EGOI 2026 publishes none): the official checker must give the
    official answer full marks and an empty output none (CMS checkers); a FrontierCS testlib checker (whose .ans
    files need not be a contestant output) must compile, end with a testlib exit code and give an empty output 0."""
    import ladder_judge as J
    j = meta["judge"]
    if j["kind"] not in ("checker", "testlib") or j.get("interactor"):
        return None
    src = [j["checker"]] if j["kind"] == "testlib" else [os.path.basename(j.get("source") or j.get("checker"))]
    cb, log = J._compile_once(meta, "checker", src, "checker")
    if not cb:
        return {"ok": False, "why": "checker does not compile: " + log[-300:]}
    d = os.path.join(L.PROBLEMS, meta["pid"])
    work = L.tmpdir("chk_selftest_")
    try:
        empty = os.path.join(work, "empty.txt")
        open(empty, "w").close()
        res = []
        for t in meta["tests"][:n]:
            inp, ans = os.path.join(d, "tests", t["in"]), os.path.join(d, "tests", t["out"])
            if j["kind"] == "checker":
                full, _ = L.run_checker("cms", cb, inp, ans, ans, work)
                none, _ = L.run_checker("cms", cb, inp, empty, ans, work)
                res.append(full >= 1 - 1e-9 and none == 0)
            else:
                import subprocess
                p = subprocess.run([cb, inp, empty, ans], capture_output=True, text=True, cwd=work, timeout=60)
                # a testlib exit code (0 ok, 1 wa, 2 pe, 3 fail, 7 points; many FrontierCS checkers FAIL on an
                # empty output, which the official judge also scores 0), and an empty output never scores
                score = L.interactor_score(p.returncode << 8, p.stdout + p.stderr) if p.returncode in (0, 7) else 0.0
                res.append(p.returncode in (0, 1, 2, 3, 7) and score == 0)
        return {"ok": bool(res) and all(res), "tests": len(res)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def calibrate(pid, workers=8):
    """Judge every reference candidate of a problem; keep those that pass every test (lenient limit), record their
    CPU times, and pick the fastest per language as the reference for the performance ratios."""
    import ladder_judge as J
    meta = L.load_meta(pid)
    d = os.path.join(L.PROBLEMS, pid)
    res = {}
    for c in meta.get("ref_candidates", []):
        code = open(os.path.join(d, "ref", c["file"])).read()
        # 2x the official limit is plenty for an official solution, and partial (subtask) solutions in the
        # editorials then fail in 2x instead of burning the 5x lenient limit on every big test
        r = J.judge_code(meta, code, c["lang"], workers=workers, lenient=float(os.environ.get("CALIBRATE_LENIENT", "2")))
        res[c["file"]] = {"lang": c["lang"], "solved": r["solved"], "score": r["score"],
                          "strict_solved": r["strict_solved"], "max_cpu": r["max_cpu"], "total_cpu": r["total_cpu"],
                          "rss_kb": r["max_rss_kb"], "cpu": {t["name"]: t["cpu"] for t in r["tests"]},
                          "rss": {t["name"]: t.get("rss_kb", 0) for t in r["tests"]},
                          "fails": [f"{t['name']}:{t['verdict']}" for t in r["tests"] if t["score"] < 1][:5]}
    best = {}
    for f, r in res.items():
        if r["solved"] and (r["lang"] not in best or r["max_cpu"] < res[best[r["lang"]]]["max_cpu"]):
            best[r["lang"]] = f
    meta["calibration"] = res
    if not meta.get("ref_candidates"):
        st = checker_selftest(meta)
        if st is not None:
            meta["checker_selftest"] = st
            meta["verified"] = st["ok"]
            json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1, ensure_ascii=False)
            return pid, {}, {} if st["ok"] else {"checker self-test": st}
    meta["ref"] = {lang: dict(file=f, **{k: res[f][k] for k in ("max_cpu", "total_cpu", "rss_kb", "cpu", "rss", "strict_solved")})
                   for lang, f in best.items()}
    meta["verified"] = bool(best) or not meta.get("ref_candidates")
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1, ensure_ascii=False)
    return pid, {lang: f"{f} max {res[f]['max_cpu']:.3f}s" for lang, f in best.items()}, \
        {f: r["fails"] for f, r in res.items() if not r["solved"]}


# ---------------------------------------------------------------- manifest

def manifest(out, l5=30):
    """All USACO problems that are verified and need no special checker, EGOI/IOI 2026, and a fixed L5 subset:
    l5 FrontierCS problems spread over the tags (every k-th problem of each tag, by id; the v1.1 problems carry no
    tag, so this is every k-th problem by id)."""
    metas = [json.load(open(f)) for f in glob.glob(os.path.join(L.PROBLEMS, "*", "meta.json"))]
    tiers = {t: [] for t in L.TIERS}
    skipped = {}
    for m in sorted(metas, key=lambda m: (m["tier"], m["source"], m["date"], m["pid"])):
        if m["source"] == "frontiercs":
            continue
        why = ("no official solution passes our tests" if m.get("verified") is False else
               "interactive or communication task (manager/controller program): not supported by the native judge yet"
               if m["judge"]["kind"] == "communication" else
               "expected outputs are all empty, nothing to compare against"
               if m["judge"]["kind"] == "tokens" and m["tests"] and all(
                   os.path.getsize(os.path.join(L.PROBLEMS, m["pid"], "tests", t["out"])) == 0 for t in m["tests"]) else
               "multiple valid answers, no checker" if m.get("multi_answer") and m["judge"]["kind"] == "tokens" else
               "statement missing" if not os.path.exists(os.path.join(L.PROBLEMS, m["pid"], "statement.md"))
               or not open(os.path.join(L.PROBLEMS, m["pid"], "statement.md")).read().strip() else None)
        if why:
            skipped[m["pid"]] = why
        else:
            tiers[m["tier"]].append(m["pid"])
    fcs = sorted((m for m in metas if m["source"] == "frontiercs"), key=lambda m: int(m["pid"].split("-")[1]))
    by_tag = {}
    for m in fcs:
        by_tag.setdefault(m.get("tag") or "other", []).append(m["pid"])
    picked = []
    total = len(fcs)
    for tag, ps in sorted(by_tag.items()):
        k = max(1, round(l5 * len(ps) / total)) if total else 0
        step = len(ps) / k
        picked += [ps[int(i * step)] for i in range(k)]
    tiers["L5"] = sorted(picked[:l5] if len(picked) > l5 else picked, key=lambda p: int(p.split("-")[1]))
    info = {p: {k: m.get(k) for k in ("tier", "source", "subset", "title", "contest", "date", "lang", "tl", "ml")}
            for m in metas for p in [m["pid"]] if any(p in v for v in tiers.values())}
    json.dump({"version": "ladder-v1", "tiers": tiers, "skipped": skipped, "problems": info,
               "l5_pool": len(fcs)}, open(out, "w"), indent=1, ensure_ascii=False)
    for t in L.TIERS:
        print(t, len(tiers[t]))
    print("skipped", skipped)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="usaco,egoi2026,ioi2026,frontiercs")
    ap.add_argument("--only", default="")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--missing", action="store_true", help="with --calibrate: only problems not calibrated yet")
    ap.add_argument("--manifest")
    ap.add_argument("--l5", type=int, default=30)
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    if a.manifest:
        return manifest(a.manifest, a.l5)
    if a.calibrate:
        def wanted(p):
            m = json.load(open(os.path.join(p, "meta.json")))
            st = os.path.join(p, "statement.md")
            if m["judge"]["kind"] == "communication" or not os.path.exists(st) or not open(st).read().strip():
                return False  # left out of the problem list anyway (see manifest)
            if a.missing and "calibration" in m:
                return False
            return m.get("ref_candidates") or (m["judge"]["kind"] in ("checker", "testlib") and not m["judge"].get("interactor"))
        pids = sorted(only or [os.path.basename(p) for p in glob.glob(os.path.join(L.PROBLEMS, "*")) if wanted(p)])
        per = max(1, a.workers // 4)

        def safe(p):  # one broken problem must not stop the others
            try:
                return calibrate(p, per)
            except Exception as e:  # noqa: BLE001
                return p, {}, {"calibration error": repr(e)[:300]}
        print(f"calibrating {len(pids)} problems")
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            for pid, best, bad in ex.map(safe, pids):
                print(pid, "reference:", best or "NONE", ("failed: " + json.dumps(bad)) if bad else "")
                sys.stdout.flush()
        return
    for s in a.sources.split(","):
        {"usaco": build_usaco, "egoi2026": build_egoi, "ioi2026": build_ioi, "frontiercs": build_frontiercs}[s](only)


if __name__ == "__main__":
    main()
