# codingBench：代码能力评测

评测模型的代码能力。

| 命令名 | Benchmark | 论文 | 测什么 | 题数 |
|---|---|---|---|---|
| `bigcodebench` | BigCodeBench-Hard（Instruct） | ICLR 2025 Oral | 按自然语言需求写函数，要调用真实的库（pandas、numpy、requests、matplotlib 等） | 148 |
| `livecodebench` | LiveCodeBench release_v6 | ICLR 2025 | 竞赛编程题（LeetCode / AtCoder / Codeforces），按发布日期切分，可以只算模型训练截止之后的新题 | 1055 |
| `cruxeval` | CRUXEval 的 input 和 output 两项 | ICML 2024 | 读代码推理：给定函数和输出，写出输入（input）；或给定输入，算出输出（output） | 各 800 |



## 用法

```bash
export MODEL=<平台上的模型名> OPENAI_BASE_URL=https://xxx/v1 OPENAI_API_KEY=sk-xxx
cb all --smoke      # 每个只跑 5 题左右，先确认接口和格式没问题（几分钟）
cb all              # 全量
cb livecodebench    # 也可以只跑一个
cb summary          # 所有跑完的结果
cb report <模型名>/livecodebench-full   # LiveCodeBench 的详细报告（按难度、来源、月份、失败原因）
cb usage <模型名>/livecodebench-full    # 每次 API 调用的延迟和 token（加 --price-in/--price-hit/--price-out 每百万 token 单价可算费用）
cb rejudge <模型名>/livecodebench-full  # 复核判分：AtCoder 答案用真实标准输入输出重跑全部官方测试，多解题用校验器
cb quality <模型名>/livecodebench-full  # 静态代码质量（Pylint、Radon；加 --sonar 再跑 SonarQube），按 arXiv:2610.19167 的表格输出
```

LiveCodeBench 自带的判题程序会误判：它模拟的 `sys.stdin.buffer.readline` 每次都返回输入的第一行，也不支持 `sys.stdout.buffer`，`abc397_d` 的第 41 个测试标准答案错误，`arc195_c` 允许任意合法构造却按单一答案比对。`cb rejudge` 把每份 AtCoder 答案作为独立进程运行（每个测试 6 秒），这两题用校验器，LeetCode 题沿用 LCB 判分；结果写到运行目录的 `rejudge.jsonl`，并打印复核前后的 pass@1。对比模型时用复核后的结果。

每次评测都要跑 `cb quality`，按 Huang 等人的 *Beyond Functional Correctness: Static Code Quality Profiling of LLM-Generated Code*（arXiv:2610.19167）的口径输出静态代码质量：
- 工具与版本：Pylint 3.3.5（默认配置）、Radon 6.0.1（命令行）、SonarQube 10.4 Community（可选，`--sonar`），在单独的 Python 3.12 环境 `venvs/quality` 里运行。
- 每份答案原样分析，不补 import；空答案跳过。Pylint 统计 C/R/W/E/F 各类问题数和 0–10 分；Radon 的圈复杂度是 `cc -j` 所有条目之和（类和它的方法各算一条，与论文一致），另有 MI、函数数、LOC、LLOC、SLOC、注释行、空行；SonarQube 统计可维护性、可靠性、安全三类问题数。
- 输出 `quality.jsonl`（每份答案一行）和 `quality.md`（三张表：全部答案的每份平均、只算通过答案的每份平均，均按难度分；通过答案每 100 SLOC 的问题密度）。不合成总分。表头标出方向：↑ 越大越好（Pylint 得分、MI），↓ 越小越好（各类问题数、圈复杂度），没有箭头的列（函数数、各类行数）只描述规模；写进报告或网站的表格也要这样标。“通过”用 `rejudge.jsonl` 的复核结果，没有复核时用 LCB 判分。
- SonarQube：先以 root 运行 `deploy/sonarqube.sh start`（本机 Docker 容器，只监听 127.0.0.1:9000，令牌写在 `/root/.config/code_bench/sonar.env`），再 `set -a; source /root/.config/code_bench/sonar.env; set +a; cb quality <运行目录> --sonar`，用完 `deploy/sonarqube.sh stop`。

可选的环境变量：
- `MAX_TOKENS`：每次回答的最大 token 数，默认 16384。不能超过模型的上下文长度。推理模型的思考也算在里面：思考用完了上限就交不出答案，判为失败。比如 DeepSeek-V4.1-Flash 做困难题时 65536 都不够，要设到 262144。LiveCodeBench 续跑时只重做空答案的题，所以可以先用小上限跑一遍，再调大上限重跑同一条命令。设成 `none` 就完全不传上限，模型可以一直写到上下文用满为止（目前只对 LiveCodeBench 有效）。
- `WORKERS`：同时发出的请求数，默认 16。平台限流的话调小。BigCodeBench 官方的 API 生成是一题一题串行发的，`WORKERS` 对它的生成不起作用；推理模型每题要 1–2 分钟的话，148 题要几个小时。
- `LCB_START=2025-01-01`：LiveCodeBench 只算这个日期之后发布的题，用来避开模型训练时可能见过的题。
- `LCB_RELEASE`：默认 `release_v6`，题目到 2025 年 4 月。
- `LCB_IDS=samples/lcb_newest100.txt`：只跑清单里的题（相对路径从安装目录算起）。`samples/lcb_newest100.txt` 是 release_v6 里最新的 100 题（2025-02-15 到 2025-04-06，简单 23、中等 30、困难 47）。`samples/lcb_newest35.txt` 是从这 100 题里按难度各取最新的：中等 10、困难 25（2025-03-15 到 2025-04-06，AtCoder 26、LeetCode 9），用来省钱。
- `LCB_TIMEOUT`：每个请求最多等多少秒，默认 1800。推理模型把 `MAX_TOKENS` 调得很大时要跟着调大。
- `LCB_STREAM=1`：LiveCodeBench 用流式请求。`LCB_TIMEOUT` 变成“多久收不到新 token 就算超时”，卡住的请求很快重试；运行目录里的 `usage.jsonl.live.<进程号>` 每 10 秒更新一次已收到的字符数（思考 / 回答），用来看进度。
- `LCB_OMIT`：LiveCodeBench 请求里不发送的字段，逗号分隔。有的模型把这些参数固定了，发了会报错，比如 Kimi K3.1 Pro 要设 `LCB_OMIT=temperature,top_p,n,presence_penalty,frequency_penalty`（它固定 temperature 1.0、top_p 0.95）。
- `SONAR_URL`、`SONAR_TOKEN`、`SONAR_SCANNER`：`cb quality --sonar` 用的本机 SonarQube 地址、令牌和扫描器路径（`deploy/sonarqube.sh start` 生成）。
- `CRUX_MAX_TOKENS`：CRUXEval 官方每次回答只给 100 个 token（带思维链的模式是 1000），那是给普通模型定的。推理模型的思考也算在 token 数里，会被截断成空答案，所以推理模型要设成和 `MAX_TOKENS` 一样。

结果在 `runs/<模型名>/<benchmark>-full/result.json`，模型的原始回答也在同一个目录里。某题的请求重试次数用完、或账户余额不足时，这题记为空答案（判为失败），其余题照常保存和打分；余额不足后不再发新请求。中途断了直接重跑同一条命令：已经答过的题不会再请求一次（每次都会把已有的回答重新判一遍分，在本机跑，不花钱）。



## 打分口径

- 都是 pass@1。BigCodeBench 用贪心解码（temperature 0），LiveCodeBench 和 CRUXEval 用 temperature 0.2、每题 1 次。
- 和官方排行榜的提示词、打分程序相同。CRUXEval 官方排行榜每题采样 10 次再算 pass@1，这里每题 1 次，所以单次结果会有几个点的波动。


## 目录

- `bin/cb`：入口；`bin/lcb_run.py`、`bin/crux_run.py`：在官方代码外面套的一层（不改官方代码）
- `tools/lcb_quality.py`：静态代码质量（`cb quality`）；`deploy/sonarqube.sh`：本机 SonarQube
- `tools/lcb_report.py`：LiveCodeBench 报告；`tools/lcb_usage.py`：延迟和 token 报告（读 LiveCodeBench 运行目录里的 `usage.jsonl`）
- `samples/`：固定的题目清单
- `deploy/setup.sh`：安装和更新（只在仓库里）
- `reports/`：跑过的评测报告（例如 `2026-10-19_lcb_newest100.md`：DeepSeek-V4.1-Flash 对比 Qwen2.5-3B）
- 结果网站：https://bai-ai-lab.github.io/coding-eval/（公开仓库 `BAI-AI-Lab/coding-eval`）。由 `reports/2026-10-23_lcb35_kimi_deepseek/site.py` 生成：在放好 `runs/` 的报告目录里运行 `python site.py <coding-eval 的检出目录>`（需要 pygments），然后在该目录提交并推送
- `SURVEY.md`：选这几个 benchmark 时调研过的约 45 个代码 benchmark（会议、获奖级别、怎么跑、国内能不能下）
- `src/`：三个官方仓库（`install.sh` 拉取，钉在测过的 commit 上）
- `venvs/`：每个 benchmark 一个独立的 Python 环境
- `data/code_generation_lite/`：LiveCodeBench 的题目（从 OpenCompass 的阿里云镜像下载，sha256 和 HF 官方一致）
- `runs/`：结果
