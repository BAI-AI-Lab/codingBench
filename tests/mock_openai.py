"""A stand-in OpenAI-compatible endpoint for testing the ladder pipeline end to end without paying for a model.

  CB=<install dir> python tests/mock_openai.py [--port 18999] [--wrong 0.3]

It answers every chat completion (streamed or not, with a little "reasoning_content" and a usage block) with the
reference solution of the ladder problem whose statement appears in the prompt, so a run over solvable problems
should come out solved; --wrong makes that share of answers a program that prints nothing, to exercise failures.
A multimodal ladder item (cb mm, text parts of the message) gets its correct answer; a model whose name contains
"weak" answers about half of the items wrongly (the same ones every time), so two runs differ.
"""
import argparse
import glob
import hashlib
import json
import os
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import ladder_lib as L  # noqa: E402
import mm_lib as M  # noqa: E402

INDEX = []
MM = []


def load():
    for d in glob.glob(os.path.join(L.PROBLEMS, "*")):
        try:
            meta = json.load(open(os.path.join(d, "meta.json")))
            st = open(os.path.join(d, "statement.md")).read().strip()
        except OSError:
            continue
        ref = (meta.get("ref") or {}).get(meta["lang"])
        f = ref["file"] if ref else next((c["file"] for c in meta.get("ref_candidates", []) if c["lang"] == meta["lang"]), None)
        code = open(os.path.join(d, "ref", f)).read() if f else ("print()\n" if meta["lang"] == "python" else "int main(){}\n")
        INDEX.append((st[:300], meta["lang"], code))
    for d in glob.glob(os.path.join(M.ITEMS, "*")):
        try:
            it = json.load(open(os.path.join(d, "item.json")))
        except OSError:
            continue
        MM.append((M.prompt_text(it), it))


def mm_answer(it, weak):
    t, gold = it["answer_type"], it["answer"]
    wrong = weak and int(hashlib.sha1(it["id"].encode()).hexdigest(), 16) % 2 == 0
    if t == "point_in_box":
        x1, y1, x2, y2 = it["box"]
        w, h = it["size"]
        x, y = ((x1 + x2) / 2 / w * 1000, (y1 + y2) / 2 / h * 1000) if not wrong else (999, 999)
        return f"The target is here.\nAnswer: ({x:.0f}, {y:.0f})"
    if t == "point_in_mask":
        y, runs = next(iter(it["mask"].items()))
        w, h = it["size"]
        x = (runs[0][0] + runs[0][1]) / 2 if not wrong else w - 1
        return f"It is here.\nAnswer: ({x / w * 1000:.0f}, {(int(y) + 0.5) / h * 1000:.0f})"
    g = gold[0] if isinstance(gold, list) else gold
    if wrong:
        g = {"mcq": "A" if g != "A" else "B", "yesno": "no" if str(g).lower() == "yes" else "yes"}.get(t, "zzz")
    return f"Looking at the image.\nAnswer: {g}"


def text_of(content):
    return content if isinstance(content, str) else "\n".join(p.get("text", "") for p in content if p.get("type") == "text")


def answer(prompt, wrong, model=""):
    for key, it in MM:
        if key in prompt:
            return mm_answer(it, "weak" in model)
    for key, lang, code in INDEX:
        if key and key in prompt:
            if random.random() < wrong:
                code = "pass\n" if lang == "python" else "int main(){return 0;}\n"
            return f"Here is my solution.\n```{'python' if lang == 'python' else 'cpp'}\n{code}```\n"
    return "I do not know this problem."


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = text_of(body["messages"][-1]["content"])
        text = answer(prompt, self.server.wrong, body["model"])
        usage = {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4 + 50,
                 "completion_tokens_details": {"reasoning_tokens": 50}}
        if not body.get("stream"):
            out = {"id": "x", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
                   "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
                   "usage": usage}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def chunk(delta, finish=None, use=None):
            c = {"id": "x", "object": "chat.completion.chunk", "created": int(time.time()), "model": body["model"],
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish}] if delta is not None else []}
            if use:
                c["usage"] = use
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
            self.wfile.flush()
        chunk({"role": "assistant", "reasoning_content": "Let me think about the problem. "})
        for i in range(0, len(text), 200):
            chunk({"content": text[i:i + 200]})
        if body["model"] == "mock-cut":  # the server drops the stream: no finish_reason, no usage
            self.wfile.write(b"data: [DONE]\n\n")
            return
        chunk({}, finish="stop")
        chunk(None, use=usage)
        self.wfile.write(b"data: [DONE]\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18999)
    ap.add_argument("--wrong", type=float, default=0.0)
    a = ap.parse_args()
    load()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    srv.wrong = a.wrong
    print(f"mock endpoint on http://127.0.0.1:{a.port}/v1 with {len(INDEX)} problems", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
