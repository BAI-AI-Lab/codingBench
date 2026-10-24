"""Streaming in bin/lcb_run.py on fake streams (no LiveCodeBench, no network; needs the openai package).

  python tests/test_lcb_stream.py

Checks that thinking and answer are put back together with their first-token times, that each logged call carries its
question_id from problems.json, that Kimi's usage on the choice is read, that a stream ending without a finish reason
is a retryable connection error (not a cut-off answer), that a timeout while reading becomes an APITimeoutError, and
that an endpoint rejecting stream_options is asked again without it.
"""
import json
import os
import sys
import tempfile
import types

import httpx
import openai

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
for k in ("STREAM", "LCB_STREAM", "LCB_IDS", "MAX_TOKENS", "LCB_OMIT"):
    os.environ.pop(k, None)
os.environ.update(MODEL="m", CB=tmp, LCB_USAGE_LOG=os.path.join(tmp, "usage.jsonl"))


def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(sys.modules[parent], child, m)
    return m


FAKE = []  # the stream (or exception) the next create() returns, and the kwargs it was called with
CALLS = []


class Completions:
    def create(self, *args, **kwargs):
        CALLS.append(kwargs)
        out = FAKE.pop(0)
        if isinstance(out, Exception):
            raise out
        return iter(out)


class Client:
    base_url = "http://fake/v1"

    def __init__(self):
        self.chat = types.SimpleNamespace(completions=Completions())

    def with_options(self, **kwargs):
        return self


class OpenAIRunner:
    client = Client()

    def __init__(self, *args, **kwargs):
        self.client_kwargs = {}

    def _run_single(self, prompt, n=10):
        return []


PROBS = [types.SimpleNamespace(question_id="p1", question_title="T1", platform=types.SimpleNamespace(value="atcoder"),
                               difficulty=types.SimpleNamespace(value="hard"), question_content=" Count the pairs. "),
         types.SimpleNamespace(question_id="p2", question_title="T2", platform=types.SimpleNamespace(value="leetcode"),
                               difficulty=types.SimpleNamespace(value="medium"), question_content="Sort the array.")]
module("datasets", load_dataset=lambda *a, **k: None)
module("lcb_runner")
module("lcb_runner.lm_styles", LanguageModel=lambda *a: a, LMStyle=types.SimpleNamespace(OpenAIChat="chat"),
       LanguageModelList=[], LanguageModelStore={})
module("lcb_runner.benchmarks", load_code_generation_dataset=lambda *a, **k: list(PROBS))
module("lcb_runner.runner")
module("lcb_runner.runner.oai_runner", OpenAIRunner=OpenAIRunner)
module("lcb_runner.runner.main", main=lambda: None)
sys.path.insert(0, os.path.join(HERE, "..", "bin"))
import lcb_run  # noqa: E402

assert lcb_run.STREAM  # streaming is the default
lcb_run._bm.load_code_generation_dataset()  # what scenario_router calls: writes problems.json
index = json.load(open(os.path.join(tmp, "problems.json")))
assert [(p["q"], p["platform"], p["difficulty"], p["content"]) for p in index] == [
    ("p1", "atcoder", "hard", "Count the pairs."), ("p2", "leetcode", "medium", "Sort the array.")], index


def chunk(content=None, think=None, finish=None, usage=None, choice_usage=None):
    delta = types.SimpleNamespace(content=content, reasoning_content=think, model_extra={})
    c = types.SimpleNamespace(delta=delta, finish_reason=finish, model_extra={"usage": choice_usage} if choice_usage else {})
    return types.SimpleNamespace(model="m-1", usage=usage, choices=[c])


def logged():
    return [json.loads(l) for l in open(os.environ["LCB_USAGE_LOG"])]


create = lcb_run._completions.create
msgs = [{"role": "user", "content": "### Question:\nCount the pairs.\n### Answer:"}]
kimi_usage = {"completion_tokens": 9, "prompt_tokens": 5}
FAKE.append([chunk(think="let me "), chunk(think="think"), chunk(content="print("), chunk(content="1)"),
             chunk(finish="stop", choice_usage=kimi_usage)])
r = create(messages=msgs, model="m")
assert r.choices[0].message.content == "print(1)" and r.choices[0].finish_reason == "stop"
assert CALLS[-1]["stream"] is True and CALLS[-1]["stream_options"] == {"include_usage": True}
rec = logged()[-1]
assert rec["q"] == "p1" and rec["stream"] and rec["usage"] == kimi_usage and rec["reasoning_chars"] == 12, rec
assert rec["start"] <= rec["first_token"] <= rec["first_content"] <= rec["end"], rec
assert rec["content"] == ["print(1)"] and rec["finish"] == ["stop"]

# the server closes the stream without finishing: LCB must see a retryable error, not a cut-off answer
FAKE.append([chunk(think="hmm"), chunk(content="print(")])
try:
    create(messages=msgs, model="m")
    raise AssertionError("a stream without finish_reason was accepted")
except openai.APIConnectionError:
    pass
rec = logged()[-1]
assert "error" in rec and rec["q"] == "p1" and rec["reasoning_chars"] == 3 and rec["content_chars"] == 6, rec

# a read timeout in the middle of the stream: LCB retries openai errors only
req = httpx.Request("POST", "http://fake/v1/chat/completions")


def stalled():
    yield chunk(think="a")
    raise httpx.ReadTimeout("idle", request=req)


FAKE.append(stalled())
try:
    create(messages=[{"role": "user", "content": "Sort the array."}], model="m")
    raise AssertionError("a stalled stream was accepted")
except openai.APITimeoutError:
    pass
assert logged()[-1]["q"] == "p2"

# an endpoint that rejects stream_options: asked again without it, and not again afterwards
bad = openai.BadRequestError("Unrecognized request argument: stream_options", body=None,
                             response=httpx.Response(400, request=req))
FAKE += [bad, [chunk(content="x"), chunk(finish="stop", usage={"completion_tokens": 1})]]
r = create(messages=msgs, model="m")
assert r.choices[0].message.content == "x" and "stream_options" not in CALLS[-1] and lcb_run._no_stream_options
FAKE.append([chunk(content="y"), chunk(finish="length")])
r = create(messages=msgs, model="m")
assert "stream_options" not in CALLS[-1] and r.choices[0].finish_reason == "length"
assert not [f for f in os.listdir(tmp) if ".live." in f]  # live files are removed when a request ends
print("ok")
