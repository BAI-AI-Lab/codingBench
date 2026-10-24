"""CRUXEval for an OpenAI-compatible model, using the repo's own prompts (prompts.py), answer extraction
(openai/openai_prompt.py) and scorer (evaluation/). The official openai_run.py hard-codes its model list and
asks for n=10 per call; this asks for one completion per call, so it works on endpoints that reject n>1.

  crux_run.py --mode input|output [--cot] [--n 1] [--temperature 0.2] [--limit N] [--workers 16] --out DIR
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

REPO = os.path.join(os.environ["CB"], "src", "cruxeval")
sys.path[:0] = [REPO, os.path.join(REPO, "openai"), os.path.join(REPO, "evaluation")]
import prompts  # noqa: E402
import openai_prompt as op  # noqa: E402
from utils_general import evaluate_score, pass_at_k  # noqa: E402
from openai import OpenAI  # noqa: E402

SYSTEM = "You are an expert at Python programming, code execution, test case generation, and fuzzing."
MAKE = {(False, "input"): (prompts.make_direct_input_prompt, op.extract_answer_direct_input),
        (True, "input"): (prompts.make_cot_input_prompt, op.extract_answer_cot_input),
        (False, "output"): (prompts.make_direct_output_prompt, op.extract_answer_direct_output),
        (True, "output"): (prompts.make_cot_output_prompt, op.extract_answer_cot_output)}

ap = argparse.ArgumentParser()
ap.add_argument("--mode", required=True, choices=["input", "output"])
ap.add_argument("--cot", action="store_true")
ap.add_argument("--n", type=int, default=1)
ap.add_argument("--temperature", type=float, default=0.2)
ap.add_argument("--max_tokens", type=int, default=None, help="default: 100 direct / 1000 cot, as in the repo")
ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--workers", type=int, default=16)
ap.add_argument("--out", required=True)
a = ap.parse_args()

data = [json.loads(l) for l in open(os.path.join(REPO, "data", "cruxeval.jsonl"))]
if a.limit:
    data = data[:a.limit]
make, extract = MAKE[(a.cot, a.mode)]
max_tokens = a.max_tokens or (1000 if a.cot else 100)
STREAM = os.environ.get("STREAM", "1") != "0"
client = OpenAI(timeout=300 if STREAM else 600)  # streamed: the longest gap between two tokens
model = os.environ["MODEL"]
os.makedirs(a.out, exist_ok=True)
raw_path = os.path.join(a.out, "raw.jsonl")
done = {}
if os.path.exists(raw_path):  # resume: keep finished samples
    for l in open(raw_path):
        r = json.loads(l)
        done[r["id"]] = r["texts"]


def complete(**kw):
    """One answer, streamed unless STREAM=0, so a stalled request fails after 300 s without a token."""
    if not STREAM:
        return client.chat.completions.create(**kw).choices[0].message.content or ""
    parts, finish = [], None
    for ch in client.chat.completions.create(stream=True, **kw):
        for c in ch.choices:
            parts.append(c.delta.content or "")
            finish = c.finish_reason or finish
    if finish is None:  # the server closed the stream early: retry rather than keep a cut-off answer
        raise RuntimeError("stream ended without a finish_reason")
    return "".join(parts)


def ask(i):
    if i in done and len(done[i]) >= a.n:
        return i, done[i][:a.n]
    d = data[i]
    q = (d["code"], d["output"]) if a.mode == "input" else (d["code"], d["input"])
    texts = []
    for _ in range(a.n):
        for attempt in range(5):
            try:
                texts.append(complete(model=model, temperature=a.temperature, max_tokens=max_tokens, stop=["[/ANSWER]"],
                                      messages=[{"role": "system", "content": SYSTEM},
                                                {"role": "user", "content": make(q)}]))
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 4:
                    raise
                print(f"sample_{i}: {type(e).__name__}: {e}; retrying", file=sys.stderr)
                import time; time.sleep(10 * (attempt + 1))
    return i, texts


with ThreadPoolExecutor(a.workers) as ex, open(raw_path, "a") as raw:
    results = {}
    for i, texts in ex.map(ask, range(len(data))):
        results[i] = texts
        if i not in done:
            raw.write(json.dumps({"id": i, "texts": texts}) + "\n"); raw.flush()

gens = {f"sample_{i}": [extract(t) for t in results[i]] for i in range(len(data))}
json.dump(gens, open(os.path.join(a.out, "generations.json"), "w"))
refs = [(d["code"], d["input"], d["output"]) for d in data]
with ProcessPoolExecutor() as ex:
    scores = list(ex.map(evaluate_score, zip([gens[f"sample_{i}"] for i in range(len(data))], refs,
                                             [a.mode] * len(data))))
p1 = sum(pass_at_k(len(s), s.count(True), 1) for s in scores) / len(scores) * 100
res = {"benchmark": f"cruxeval-{'i' if a.mode == 'input' else 'o'}{'-cot' if a.cot else ''}", "model": model,
       "problems": len(data), "n": a.n, "temperature": a.temperature, "pass@1": round(p1, 2),
       "full_set": len(data) == 800}
json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
print(json.dumps(res))
