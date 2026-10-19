# Code-LLM benchmark survey (verified 2026-10-18)

## How this was checked

- **Venues:** taken from iclr.cc / icml.cc / neurips.cc virtual pages, conference proceedings, PMLR, ACL Anthology, ACM DL and IEEE Xplore. OpenReview's web pages returned a 403 challenge, so for some entries the venue comes from the OpenReview API `venue` field instead.
- **Awards:** I found no best or outstanding paper award for any of these. ClassEval and CoderEval are not on the ICSE 2024 Distinguished Paper list (https://conf.researchr.org/info/icse-2024/awards). I did not search every award list exhaustively.
- **Stars and licenses:** from `gh api`. "none" means the repo has no license file.
- **Leaderboard numbers:** read live on 2026-10-18. "stale" means the board stopped updating.
- **Pre-2024:** marked ⚠pre-2024.

## Main table

Column notes:
- **Venue:** the conference and how it was presented (oral, spotlight or poster).
- **No-Docker?:** whether it runs without a Docker daemon. "Container" means podman or apptainer, installed with apt, is enough.

| Benchmark | Venue | Repo (★, license) | Measures; size; languages | Time-sliced? | Official harness takes an OpenAI base_url? | No-Docker? | Data, and reachable from China? | Leaderboard top |
|---|---|---|---|---|---|---|---|---|
| **Function-level** | | | | | | | | |
| BigCodeBench | **ICLR 2025 Oral** | bigcode-project/bigcodebench (516, Apache-2.0; archived 2026-01, PyPI 0.2.5 still installs) | practical library-call tasks; 1,140, Hard subset 148; Python, 139 libraries | no | yes, `--backend openai --base_url` | yes, `--execution local` | HF and ModelScope `bigcode/bigcodebench(-hard)`; OpenCompass OSS mirror | stale since 2025-04. Full-Complete: Gemini-Exp-1206 62.4. Hard-Instruct: o3-mini 33.1 |
| EvalPlus (HumanEval+, MBPP+) | NeurIPS 2023, poster ⚠pre-2024 | evalplus/evalplus (1.8k, Apache-2.0) | 164 + 378 problems; Python | no, saturated | yes, `--backend openai --base-url` | yes | GitHub releases | stale since 2024-12; about 89 on HumanEval+ |
| HumanEval / MBPP | arXiv only ⚠ | openai/human-eval (3.4k, MIT; deprecated) | 164 / 974 problems; Python | no | use EvalPlus instead | yes | GitHub | none |
| AutoCodeBench | ICLR 2026, poster | Tencent-Hunyuan/AutoCodeBenchmark (438, NOASSERTION) | 3,920 problems (Lite 1,586; V2 1,000); 20 languages | partly | any API; you generate the outputs yourself | needs its sandbox container, image on Docker Hub only | HF `tencent/AutoCodeBenchmark` (not on ModelScope) | leaderboard published as images |
| McEval | ICLR 2025, poster | MCEVAL/McEval (48, none; README says MIT code / CC-BY-SA data) | 16k samples, 40 languages; generation, completion, explanation | no | no; you generate the outputs yourself | needs a container; image on the **Aliyun registry** | HF and ModelScope `Multilingual-Multimodal-NLP/McEval` | stale since 2024 |
| MultiPL-E | IEEE TSE 2023 (journal) ⚠ | nuprl/MultiPL-E (316) | HumanEval/MBPP in 18+ languages | no | chat script only | yes, if you install the language toolchains locally | HF `nuprl/MultiPL-E` | BigCode leaderboard |
| HumanEval-X | KDD 2023 ⚠ | zai-org/CodeGeeX (8.8k, Apache-2.0) | 820 problems; 5 languages | no | no | container or local toolchains | HF `THUDM/humaneval-x` | none; superseded |
| EvoEval | COLM 2024, Spotlight | evo-eval/evoeval (84, Apache-2.0) | 828 problems evolved from HumanEval | partly | not verified | yes | HF / GitHub | stale since 2024-04 |
| NaturalCodeBench | Findings of ACL 2024 | THUDM/NaturalCodeBench (71, none) | 402 problems, only 140 dev public; Python and Java | test set hidden | no | Docker | GitHub | static |
| ClassEval | ICSE 2024 | FudanSELab/ClassEval (154, MIT) | 100 classes; Python | no | no | yes | HF | static |
| CoderEval | ICSE 2024 | CoderEval/CoderEval (159, none) | 230 Python + 230 Java tasks | no | no | Docker image on Google Drive | GitHub + Google Drive (blocked in China) | none |
| EvoCodeBench | NeurIPS 2024 D&B, poster | seketeam/EvoCodeBench (72, Apache-2.0) | 275 repo-level tasks; Python | promised, but only one release | partly | yes | HF | abandoned |
| LiveBench (coding) | ICLR 2025 (README says Spotlight; the iclr.cc page shows Poster, so unconfirmed) | LiveBench/LiveBench (1.3k) | code generation and completion, plus agentic coding | **yes**, refreshed periodically | yes, `--api-base` | code tasks yes; agentic tasks need Docker | HF `livebench/*` | livebench.ai is JavaScript-rendered; I could not extract scores |
| **Competitive / algorithmic** | | | | | | | | |
| LiveCodeBench | ICLR 2025, poster | LiveCodeBench/LiveCodeBench (961, MIT; last commit 2025-07) | release_v6: 1,055 problems (May 2023 – Apr 2025); generation, self-repair, code execution, test-output prediction; Python | **yes, but frozen at Apr 2025** | through the `OPENAI_BASE_URL` environment variable plus one line registering the model | yes | HF and **ModelScope** `livecodebench/code_generation_lite` (4.5 GB); OpenCompass OSS mirror (3.3 GB) | stale since 2025-08. Jan–Apr 2025 window: o4-mini-high 75.8, Gemini-2.5-Pro 74.2 |
| LiveCodeBench Pro | NeurIPS 2025 D&B, poster | GavinZhengOI/LiveCodeBench-Pro (178, none; judge is AGPL-3.0) | 584 Codeforces/ICPC/IOI problems; judged in C++ | **yes** | through the `OPENAI_BASE_URL` environment variable; model name is hardcoded | the judge needs Docker (go-judge workaround, untested) | HF, gated (needs an `HF_TOKEN`); test cases about 15 GB | official site returns 404 |
| OJBench | venue unverified | He-Ren/OJBench (34, AGPL-3.0) | 232 NOI/ICPC problems; Python and C++ | no | you generate the outputs | yes, local DMOJ judge | HF | 2026-02: Gemini-3.0-pro 70.0 (C++) |
| HLCE | Findings of EMNLP 2025 | HLCE (97) | 235 ICPC World Finals / IOI problems | no | — | — | HF | stale; o4-mini 25.2 |
| APPS | NeurIPS 2021 D&B ⚠ | hendrycks/apps (541, MIT) | 10k problems; Python | no | no | yes | HF / Berkeley | none; legacy |
| CodeContests | Science 2022 (journal) ⚠ | google-deepmind/code_contests (2.2k, archived) | 165 test problems | no | no | Bazel-built executor | HF | none; legacy |
| CodeElo | arXiv only | QwenLM/CodeElo (75) | answers submitted to Codeforces | — | — | — | — | frozen; dropped |
| Aider Polyglot | **not a paper** (blog) | Aider-AI/polyglot-benchmark (224) | 225 Exercism exercises; edit-based; C++, Go, Java, JS, Python, Rust | no | yes, `OPENAI_API_BASE` | Docker recommended, or install 6 toolchains locally | GitHub | 2025-11: gpt-5 (high) 88.0 |
| **Code reasoning** | | | | | | | | |
| CRUXEval | ICML 2024, poster | facebookresearch/cruxeval (174, MIT; archived) | 800 Python functions; input prediction (I) and output prediction (O) | no | the `OPENAI_BASE_URL` environment variable works (the client is built with only an api_key) | yes | GitHub `data/cruxeval.jsonl` | stale; I 75.7 / O 82.0 (GPT-4-turbo with chain-of-thought) |
| CRUXEval-X | ACL 2025, main | — | 12.7k problems; 19 languages | no | — | — | — | — |
| CodeMMLU | ICLR 2025 | FSoft-AI4Code | about 20k multiple-choice questions | no | — | no execution needed | HF | — |
| **Data science / scientific** | | | | | | | | |
| DS-1000 | ICML 2023, poster ⚠pre-2024 (indispensable) | xlang-ai/DS-1000 (278, CC-BY-SA-4.0) | 1,000 problems across 7 Python libraries | perturbed against memorization | no; you generate the outputs | yes, in a conda environment | HF and **ModelScope** `xlangai/DS-1000`; also bundled in the repo | project page only |
| SciCode | NeurIPS 2024 D&B, poster | scicode-bench/SciCode (241, Apache-2.0) | 80 problems / 338 subproblems; 16 science fields; Python | no | yes, via inspect_ai `openai/` models | yes | HF `SciCode1/SciCode`; test_data.h5 is on Google Drive (blocked). For the official harness use HF `Srimadh/Scicode-test-data-h5` (unofficial); the OpenCompass OSS copy only works through OpenCompass | stale; o3-mini 10.8 (main) / 33.3 (subproblems) |
| DA-Code | EMNLP 2024, main | yiyihum/da-code (108, MIT) | 500 agentic data-science tasks | no | `OPENAI_API_KEY` | **Docker** | Google Drive | — |
| DSBench | ICLR 2025, poster | LiqiangJing/DSBench | 466 analysis + 74 modeling tasks | no | — | — | — | — |
| MLE-bench | **ICLR 2025 Oral** | openai/mle-bench (1.8k) | 75 Kaggle competitions | partly | you bring an agent scaffold | Docker; 24 GB GPU; 24 h per competition | Kaggle API; 3.3 TB (Lite 158 GB) | 2026-02: 64.4% any-medal (Famou-Agent + Gemini-3-Pro) |
| KernelBench | ICML 2025, poster | ScalingIntelligence/KernelBench (1.3k) | 250 PyTorch-to-CUDA tasks; fast_p metric | no | yes, through litellm | yes; **needs an NVIDIA GPU (an RTX 4090 works)** | GitHub / HF | no model board; results depend on the GPU |
| **SQL** | | | | | | | | |
| Spider 2.0 | **ICLR 2025 Oral** | xlang-ai/Spider2 (881, MIT) | Lite 547 / Snow 547 / DBT 68 tasks; enterprise SQL | no | Spider-Agent; base_url not documented | Snow and most of Lite need Snowflake/BigQuery cloud accounts (blocker); Lite's 135 SQLite tasks and DBT run offline | GitHub | Lite: 76.2 (an agent system) |
| BIRD (+ Mini-Dev) | NeurIPS 2023 D&B, **Spotlight** ⚠pre-2024 | AlibabaResearch/DAMO-ConvAI, bird-bench/mini_dev (190) | 12.7k pairs; Mini-Dev has 500 (SQLite/MySQL/PG; Mini-Dev V2 adds 270 more, for 780); test set hidden | no | Azure-only client; about a 3-line edit | yes, SQLite | **Aliyun OSS** minidev.zip (801 MB); HF `birdsql/bird_mini_dev` | test exec accuracy: 82.95 (GrainSQL) |
| BIRD-Interact | **ICLR 2026 Oral** | bird-bench/BIRD-Interact (1.0k, MIT) | 600 interactive PostgreSQL tasks | — | LiteLLM (ADK version) | **Docker Compose**; ground truth sent by mailing list | HF | GPT-5 17.0 |
| BIRD-Critic / SWE-SQL | NeurIPS 2025 main, poster | bird-bench/BIRD-CRITIC-1 (1.1k) | 1,100 SQL-debugging tasks | yes | — | — | HF | — |
| **Repo-level / agentic SWE** | | | | | | | | |
| SWE-bench (Full/Lite/Verified) | **ICLR 2024 Oral**; Verified is an OpenAI blog subset, not a paper | SWE-bench/SWE-bench (6.0k, MIT) | 2,294 / 300 / 500 tasks; Python | no. **OpenAI stopped evaluating on Verified on 2026-02-23 (contamination, flawed tests).** The OpenAI page returned 403, so this is from secondary reports | through agent scaffolds (mini-swe-agent / SWE-agent / OpenHands via LiteLLM) | local scoring needs Docker; **without Docker: run the agent under apptainer and score with sb-cli (cloud, free, quota-limited) or Modal** | HF and **ModelScope** `SWE-bench/SWE-bench_Verified`; Docker Hub images | Verified 79.2 (2025-12 entries) |
| SWE-bench Multimodal | ICLR 2025, poster | same repo | 617 tasks (v2 test: 480); JavaScript | no | same | Docker / sb-cli (`swe-bench-m`) | HF / ModelScope | 36.0 |
| SWE-bench Multilingual | no paper of its own (from the SWE-smith paper) | same repo | 300 tasks; 9 languages | no | same | Docker / Modal; **not supported by sb-cli** | HF / ModelScope | 72.7 |
| SWE-bench-Live | NeurIPS 2025 D&B, poster | microsoft/SWE-bench-Live (257, MIT) | 50 new tasks each month; Lite 300 / Verified 500; MultiLang 1,077 | **yes** | same | Docker; one image per task | HF via hf-mirror (not on ModelScope) | Lite 71.0 (2026-10) |
| SWE-rebench | NeurIPS 2025 D&B, poster (V2: ICML 2026) | SWE-rebench/SWE-bench-fork | rolling windows (about 111 tasks) | **yes** | the maintainers run a fixed scaffold themselves | Docker | HF and ModelScope `nebius/SWE-rebench` | 64.5 (Anthropic Fable 5) |
| SWE-Bench Pro | ICML 2026, poster | scaleapi/SWE-bench_Pro-os (545, MIT) | 731 public tasks (V2: 642); Python, Go, JS, TS | partly. OpenAI estimates about 30% of tasks are broken (2026-07; the OpenAI page returned 403, so this is from secondary reports) | Harbor / mini-swe-agent | Docker / Modal | HF and ModelScope | 61.5 |
| Multi-SWE-bench | NeurIPS 2025 D&B, poster | multi-swe-bench/multi-swe-bench (363, Apache-2.0) | 1,632 tasks (mini 400); 7 languages. The NeurIPS abstract says 2,132 tasks and 8 languages | no | patch scoring only | Docker | HF via hf-mirror (not on ModelScope) | stale per language |
| SWE-PolyBench | arXiv only (ICLR 2026 submission not accepted) | amazon-science/SWE-PolyBench (90) | 2,110 tasks (Verified 382); 4 languages | no | — | Docker (images on GHCR) | HF | about 51 |
| SWE-Lancer | **ICML 2025 Oral** | moved to openai/frontier-evals (1.3k, MIT) | 198 public tasks | — | `.env` key settings | Docker, 14 GB per task | Git LFS | none; too heavy |
| Commit0 | ICLR 2025, poster | commit-0/commit0 (194, MIT) | 57 libraries | no | aider via LiteLLM | Modal or Docker | HF | — |
| SWE-Gym / SWE-smith | ICML 2025 poster / NeurIPS 2025 D&B **Spotlight** | — | **training environments, not evaluation benchmarks** | | | | | dropped |
| RepoBench / CrossCodeEval | ICLR 2024 poster / NeurIPS 2023 D&B poster | Leolty/repobench (214), amazon-science/cceval (184) | completion scored by exact match / edit similarity; Python, Java (+TS, C#) | RepoBench v1.1 is date-sliced | built for base/completion models; poor fit for chat APIs | yes | HF / GitHub | none |
| **Terminal / agentic** | | | | | | | | |
| Terminal-Bench 2.0 | ICLR 2026, poster | harbor-framework/terminal-bench-2 (430) + harness harbor (6.2k, Apache-2.0) | 89 tasks; now continuous (v4.0 2026-08) | refreshed by version | yes, `-m openai/<model>` via LiteLLM | **`-e podman` / `-e singularity`** locally, or the Daytona/Modal/E2B cloud | Harbor Hub / GitHub; task images built from Docker Hub base images | tbench.ai shows only 4.0 now (no live 2.0 board): 64.8 (Claude Code + Opus 5.5) |
| **Security** | | | | | | | | |
| BaxBench | ICML 2025, **Spotlight** | logic-star-ai/baxbench (105, MIT) | 392 backend-app tasks; functional and security scoring | no | via OpenRouter path | **Docker** | HF | secure-pass@1 56.1 (Opus 4.5 Thinking) |
| CyberGym | **ICLR 2026 Oral** | sunblaze-ucb/cybergym (958) | 1,507 vulnerability PoC tasks | partly | bring your own agent | Docker; 240 GB to 10 TB | HF | about 20% |

### Distinctions, collected
- **Orals:**
  - ICLR 2024: SWE-bench
  - ICLR 2025: BigCodeBench, Spider 2.0, MLE-bench
  - ICML 2025: SWE-Lancer
  - ICLR 2026: BIRD-Interact, CyberGym
- **Spotlights:**
  - NeurIPS 2023 D&B: BIRD
  - COLM 2024: EvoEval
  - ICML 2025: BaxBench
  - NeurIPS 2025 D&B: SWE-smith
- **Best or outstanding paper awards:** none found.

Venue source URLs: SWE-bench https://iclr.cc/virtual/2024/oral/19757 · BigCodeBench https://iclr.cc/virtual/2025/session/31954 + https://proceedings.iclr.cc/paper_files/paper/2025/hash/a6a90bcc2aa470c3871b2d39a67d26e8-Abstract-Conference.html · Spider 2.0 https://iclr.cc/virtual/2025/oral/31826 · MLE-bench https://iclr.cc/virtual/2025/oral/31914 · SWE-Lancer https://icml.cc/virtual/2025/oral/47172 · BIRD-Interact https://iclr.cc/virtual/2026/oral/10007487 · CyberGym https://iclr.cc/virtual/2026/oral/10011728 · BIRD https://neurips.cc/virtual/2023/poster/73529 · BaxBench https://icml.cc/virtual/2025/poster/44337 · SWE-smith https://proceedings.neurips.cc/paper_files/paper/2025/hash/8b86cf5ace600c48fd188efbb8dedec8-Abstract-Datasets_and_Benchmarks_Track.html · EvoEval https://2024.colmweb.org/AcceptedPapers.html · LiveCodeBench https://iclr.cc/virtual/2025/poster/29033 · LCB Pro https://neurips.cc/virtual/2025/loc/san-diego/poster/121627 · CRUXEval https://icml.cc/virtual/2024/poster/34526 · McEval https://iclr.cc/virtual/2025/poster/29445 · AutoCodeBench https://iclr.cc/virtual/2026/poster/10008244 · DS-1000 https://icml.cc/virtual/2023/poster/25042 · SciCode https://neurips.cc/virtual/2024/poster/97822 · KernelBench https://icml.cc/virtual/2025/poster/43517 · SWE-bench-Live https://neurips.cc/virtual/2025/poster/121677 · SWE-rebench https://neurips.cc/virtual/2025/poster/121472 · Multi-SWE-bench https://neurips.cc/virtual/2025/poster/121692 · SWE-Bench Pro https://icml.cc/virtual/2026/poster/61047 · Terminal-Bench https://iclr.cc/virtual/2026/poster/10008736 · SWE-bench MM https://iclr.cc/virtual/2025/poster/28177 · EvalPlus https://neurips.cc/virtual/2023/poster/72990 · ClassEval https://dl.acm.org/doi/10.1145/3597503.3639219 · NaturalCodeBench https://aclanthology.org/2024.findings-acl.471 · DA-Code https://aclanthology.org/2024.emnlp-main.748/ · HLCE https://aclanthology.org/2025.findings-emnlp.1152/ · CRUXEval-X https://aclanthology.org/2025.acl-long.1158/

## Recommended suite (all covered abilities, runnable without a Docker daemon)

| # | Ability | Benchmark | Venue | Why this one |
|---|---|---|---|---|
| 1 | Function-level generation and library use (incl. data-science libraries) | **BigCodeBench-Hard Instruct (148)**, optionally Full (1,140) | ICLR 2025 Oral | Least saturated function-level benchmark, native `--base_url`, local execution |
| 2 | Competitive / algorithmic (time-sliced) | **LiveCodeBench release_v6**, scored on the newest window | ICLR 2025 poster | Standard contamination-aware benchmark; on ModelScope; no Docker |
| 3 | Code reasoning / execution | **CRUXEval-I/O (800)**; the LCB `codeexecution` scenario is a time-sliced complement | ICML 2024 poster | Separates "can write code" from "can simulate code"; about 1 minute to score |
| 4 | Repo-level agentic issue fixing | **SWE-bench Verified (500)**, agent in apptainer, scored by sb-cli | ICLR 2024 Oral | The most-reported agentic number. Add SWE-bench-Live Lite if a container runtime with Docker Hub access works |
| 5 | Multilingual | **McEval generation task** (40 languages) | ICLR 2025 poster | The only multilingual benchmark here whose sandbox image is on a China-hosted registry (Aliyun) |
| 6 | Data science | **DS-1000** ⚠pre-2024 | ICML 2023 poster | Still the standard; on ModelScope; no Docker. SciCode is an optional add-on for scientific code |
| opt. | SQL | **BIRD Mini-Dev (500, SQLite)** ⚠pre-2024 | NeurIPS 2023 D&B Spotlight | Data comes from Aliyun OSS; pure SQLite. Spider 2.0 needs cloud database accounts |
| opt. | Terminal / agentic shell | **Terminal-Bench 2.0 (89)** | ICLR 2026 poster | Harbor runs it with `-e podman`, no Docker daemon needed |

**If you can install a container runtime:**
- You have root, so `apt install podman` or `apt install docker.io` from a Tsinghua/Aliyun Ubuntu mirror takes a few minutes.
- The real blocker is Docker Hub access. Configure a registry mirror; I have not tested one.
- With that in place, add SWE-bench-Live, AutoCodeBench and Aider Polyglot.

## Install and run notes

**None of these commands were run on a server.** They are assembled from the READMEs and source code. Items marked (untested) have not been checked at all.

Common setup:
```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
export HF_ENDPOINT=https://hf-mirror.com
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=http://HOST:PORT/v1
MODEL=<model-id-on-endpoint>
```
- The default token limits in these harnesses are too small for reasoning models. Raise them as shown below.
- Model-generated code runs on the host. Use a dedicated non-root user or VM.

### 1. BigCodeBench
- **Install:**
  - The pip package hard-depends on vllm, so skip its dependencies.
  - The evaluation requirements file installs about 70 libraries (TensorFlow, sklearn, matplotlib, …); budget about 5 GB.
```bash
pip install bigcodebench==0.2.5 --no-deps
pip install appdirs fire multipledispatch pqdm tempdir termcolor tqdm tree_sitter tree-sitter-python wget datasets transformers numpy rich openai gradio-client e2b
git clone https://github.com/bigcode-project/bigcodebench && pip install -r bigcodebench/Requirements/requirements-eval.txt   # raw.githubusercontent.com is often blocked in China
```
  The `--no-deps` route is untested: the package may import vllm, anthropic or google-genai lazily. If so, `pip install anthropic google-genai mistralai<1` too.
- **Data:** HF `bigcode/bigcodebench-hard`, split `v0.1.4`, a few MB. It is on ModelScope too, or set `BIGCODEBENCH_OVERRIDE_PATH` to a local jsonl.
- **Run:**
```bash
bigcodebench.evaluate --model $MODEL --backend openai --base_url $OPENAI_BASE_URL \
  --split instruct --subset hard --execution local --greedy --max_new_tokens 16384 --parallel 32
```
- **Execution:** the default `gradio` backend calls an HF Space, which is blocked in China. Always pass `--execution local`.
- **Time:** not measured for `local`. The README gives 15–20 minutes for Hard on e2b.

### 2. LiveCodeBench
- **Install:**
```bash
git clone https://github.com/LiveCodeBench/LiveCodeBench && cd LiveCodeBench
pip install -e .
pip install "datasets<4"   # datasets 4.0 dropped loading scripts
```
  `pip install -e .` pulls in torch and vllm.
- **Data:** 4.5 GB, downloaded in full whichever version you pick. Two routes:
  - `modelscope download --dataset livecodebench/code_generation_lite --local_dir ./lcb_data`, then change `load_dataset("livecodebench/code_generation_lite", ...)` on line 125 of `lcb_runner/benchmarks/code_generation.py` to `"./lcb_data"` (untested). Simplest is `HF_ENDPOINT=https://hf-mirror.com` with no edit.
  - The OpenCompass OSS zip: `http://opencompass.oss-cn-shanghai.aliyuncs.com/datasets/data/code_generation_lite.zip` (3.3 GB, contains test.jsonl through test6.jsonl).
- **Register the model:** add one line to `LanguageModelList` in `lcb_runner/lm_styles.py`:
  `LanguageModel("$MODEL", "$MODEL", LMStyle.OpenAIChat, datetime(2025,1,1)),`
- **Run:**
```bash
export OPENAI_KEY=$OPENAI_API_KEY      # LCB reads OPENAI_KEY; the SDK reads OPENAI_BASE_URL
python -m lcb_runner.runner.main --model $MODEL --scenario codegeneration --release_version release_v6 \
  --n 1 --temperature 0.2 --max_tokens 16384 --openai_timeout 600 --multiprocess 16 --evaluate --num_process_evaluate 16
```
- **Contamination:** for 2026 models, report the `v6` window (Jan–Apr 2025, 175 problems). Even that window predates most 2026 training cutoffs.

### 3. CRUXEval
- **Install:**
```bash
git clone https://github.com/facebookresearch/cruxeval && cd cruxeval
pip install -r requirements-base.txt openai
```
  Data ships in the repo at `data/cruxeval.jsonl`.
- **Generate:** in `openai/openai_run.py`, set `models=["$MODEL"]`, `temperatures=[0.2]`, and `cots` as you like. Raise `max_tokens` (100 direct / 1000 chain-of-thought) for reasoning models. `n=10` per call: if the endpoint rejects `n>1`, set n=1 and report pass@1. Then:
```bash
cd openai && python openai_run.py
```
  `OPENAI_BASE_URL` is honored.
- **Score:**
```bash
cd ../evaluation && python evaluate_generations.py --generations_path ../model_generations/<run>/generations.json \
  --scored_results_path out.json --mode input   # then repeat with --mode output
```

### 4. SWE-bench Verified (no Docker daemon)
- **Install:**
```bash
pip install mini-swe-agent sb-cli
apt install -y apptainer   # pulls one docker://swebench/sweb.eval.x86_64.<id> image per instance (500); total size not measured; needs Docker Hub access or a mirror
```
- **Data:** on ModelScope as `SWE-bench/SWE-bench_Verified`, or via hf-mirror.
- **Run the agent:**
```bash
export MSWEA_SINGULARITY_EXECUTABLE=apptainer MSWEA_COST_TRACKING=ignore_errors
mini-extra swebench -m openai/$MODEL -c swebench.yaml -c model.model_kwargs.api_base=$OPENAI_BASE_URL \
  -c model.model_kwargs.custom_llm_provider=openai --subset verified --split test \
  --environment-class singularity -w 8 -o runs/$MODEL      # (untested) smoke-test first with --slice 0:5
```
- **Score with sb-cli:**
```bash
sb-cli gen-api-key you@example.com && sb-cli verify-api-key <code>
sb-cli submit swe-bench_verified test --predictions_path runs/$MODEL/preds.json --run_id $MODEL-r1
sb-cli get-report swe-bench_verified test $MODEL-r1
```
- **sb-cli limits:** it is free but quota-limited (test-split runs refresh every 30 days; email support@swebench.com for more). It does not support the Multilingual or Live splits. The alternative is `python -m swebench.harness.run_evaluation ... --modal true`, which needs a paid Modal account.
- **Cost:** API tokens are the main cost; I have no measured per-instance figure.
- **Contamination:** OpenAI stopped evaluating on Verified on 2026-02-23 (contamination, flawed tests; from secondary reports, the page returned 403). Report it for comparability only.

### 5. McEval
- **Container (no Docker daemon needed):**
```bash
apt install -y podman
podman pull registry.cn-hangzhou.aliyuncs.com/mceval/mceval:v1
```
- **Data:** HF or ModelScope `Multilingual-Multimodal-NLP/McEval`.
- **Generate:** there is no API script. Write a short loop that sends each `instruction` to the endpoint and saves `raw_generation`. Split the output into one file per language (`CPP.jsonl`, `Python.jsonl`, …) with `inference/split_result.py`.
- **Score:** inside the container:
```bash
podman run -it -v $PWD:/work registry.cn-hangzhou.aliyuncs.com/mceval/mceval:v1 bash
cd /work/eval && bash scripts/eval_generation.sh   # point the script at your folder
```
- **No container at all:** use MultiPL-E with local toolchains (`apt install g++ openjdk-21-jdk nodejs golang rustc ...`, then `evaluation/src/main.py`). Its venue is a journal (TSE).

### 6. DS-1000
- **Install:**
```bash
git clone https://github.com/xlang-ai/DS-1000 && cd DS-1000
conda env create -f environment.yml && conda activate ds1000-3.10
pip install datasets tqdm
```
  `environment.yml` brings pinned numpy/pandas/scipy/sklearn/matplotlib/TF/torch.
- **Data:** `data/ds1000.jsonl.gz` in the repo, or ModelScope `xlangai/DS-1000`.
- **Generate:** query the endpoint with each `prompt` and save in the format of `data/codex002-answers.jsonl`.
- **Score:** `python test_ds1000.py` (point it at your answers file).
- **Optional SciCode:**
  - **Official harness:** needs a single `test_data.h5`. The original is on Google Drive (blocked in China). HF `Srimadh/Scicode-test-data-h5` is an unofficial copy; check it with `-T mode=gold`, which should score 100%.
  - **OpenCompass route:** OpenCompass's OSS `scicode.zip` (391 MB) holds per-step `test_data/<id>.h5` files. These only work with OpenCompass's own SciCode config, not the official harness.
```bash
pip install -e . inspect_ai
inspect eval eval/inspect_ai/scicode.py --model openai/$MODEL -T h5py_file=eval/data/test_data.h5 --temperature 0   # (untested) assumes inspect's openai provider reads OPENAI_BASE_URL
```

### Optional: BIRD Mini-Dev
- **Data:** `wget https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip` (801 MB, Aliyun).
- **Client edit:** in `llm/src/gpt_request.py`, replace the `AzureOpenAI(...)` call in `init_client` with `OpenAI(api_key=..., base_url=$OPENAI_BASE_URL)`. Raise `max_tokens` from 512 and drop the newline stop sequence for reasoning models.
- **Run:** `sh llm/run/run_gpt.sh`, then `cd evaluation && sh run_evaluation.sh`. The metrics are EX, R-VES and Soft-F1.

### Optional: Terminal-Bench 2.0
```bash
uv tool install harbor   # PyPI package `harbor` 0.24.0 exists
apt install -y podman
OPENAI_API_KEY=$OPENAI_API_KEY OPENAI_API_BASE=$OPENAI_BASE_URL \
  harbor run -d terminal-bench@2.0 -a terminus-2 -m openai/$MODEL -e podman -n 8
# for a score comparable to the live tbench.ai board (4.0): -d terminal-bench/terminal-bench@latest
```
- Task images build from Docker Hub base images, so you need a registry mirror.
- Cloud alternative: `-e daytona` with `DAYTONA_API_KEY`.
- The `OPENAI_API_BASE` pass-through for terminus-2 is untested.

### Unified alternative: OpenCompass
- open-compass/opencompass (7.5k★, Apache-2.0) has configs for BigCodeBench, LiveCodeBench, LCB Pro, CRUXEval, DS-1000, SciCode, HumanEval+/MBPP+ and MultiPL-E.
- It pulls datasets from **Aliyun OSS (Shanghai)**, so there are no HF problems.
- It supports API models; I did not check which model class handles a custom base_url.
- Caveats:
  - Its MultiPL-E evaluator calls an HF Space, which is blocked in China.
  - Its scores are not byte-comparable with the official leaderboards (different prompts and post-processing).
