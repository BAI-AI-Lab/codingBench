# codingBench：代码能力评测

评测模型的代码能力。

| 命令名 | Benchmark | 论文 | 测什么 | 题数 |
|---|---|---|---|---|
| `bigcodebench` | BigCodeBench-Hard（Instruct） | ICLR 2025 Oral | 按自然语言需求写函数，要调用真实的库（pandas、numpy、requests、matplotlib 等） | 148 |
| `livecodebench` | LiveCodeBench release_v6 | ICLR 2025 | 竞赛编程题（LeetCode / AtCoder / Codeforces），按发布日期切分，可以只算模型训练截止之后的新题 | 1055 |
| `cruxeval` | CRUXEval 的 input 和 output 两项 | ICML 2024 | 读代码推理：给定函数和输出，写出输入（input）；或给定输入，算出输出（output） | 各 800 |
| `ladder` | 阶梯测试集（见下） | USACO、EGOI/IOI 2026、FrontierCS（ICML 2026） | 按人类难度分 5 档的竞赛题，测正确率、部分分、官方时限下的速度和相对官方解的运行时间 | L1–L4 约 98、L5 30（题库 180） |



## 用法

```bash
export MODEL=<平台上的模型名> OPENAI_BASE_URL=https://xxx/v1 OPENAI_API_KEY=sk-xxx
cb all --smoke      # 每个只跑 5 题左右，先确认接口和格式没问题（几分钟）
cb all              # 全量
cb livecodebench    # 也可以只跑一个
cb summary          # 所有跑完的结果（LiveCodeBench 同时列出 LCB 自带判分和复核后的分数）
cb progress <模型名>/livecodebench-full --watch 30   # 跑的过程中看进度：已答题数、出错、每个进行中的请求用了多久、收到多少思考和回答（加 --text 显示最新的文字）
cb report <模型名>/livecodebench-full   # LiveCodeBench 的详细报告（按难度、来源、月份、失败原因）
cb usage <模型名>/livecodebench-full    # 延迟、首个 token 时间、输出速度、token、费用和每道通过题的费用，写到 usage.md 和 usage.json（单价见下面的 PRICE_*）
cb rejudge <模型名>/livecodebench-full  # 复核判分：AtCoder 答案用真实标准输入输出重跑全部官方测试，多解题用校验器
cb quality <模型名>/livecodebench-full  # 静态代码质量（Pylint、Radon；加 --sonar 再跑 SonarQube），按 arXiv:2610.19167 的表格输出
cb perf <模型名>/livecodebench-full     # 通过的答案在官方测试上的 CPU 时间和峰值内存（每次新进程、绑核、校验输出）
cb perf <模型A>/<运行> <模型B>/<运行>    # 几个运行放在一起交替测，按“相对最快者的倍数”对比（--out 存成文件）
cb post <模型名>/livecodebench-full     # 对一个运行补跑全部后处理：rejudge、usage、quality、perf
```

`cb livecodebench`（以及 `cb all`）跑完生成和判分后，会自动依次运行 `cb rejudge`、`cb usage`、`cb quality`（设了 `SONAR_URL` 就加 `--sonar`）和 `cb perf`，结果都写在运行目录里：`rejudge.jsonl`、`usage.md`/`usage.json`、`quality.md`/`quality.jsonl`、`perf.md`/`perf.json`/`perf.jsonl`。某一步失败只打印出错，不影响其他步骤和已经保存的结果。设 `CB_POST=0` 可以跳过，之后再用 `cb post` 补跑。所有表格都标出方向：↑ 越大越好，↓ 越小越好，没有箭头的只作描述。

LiveCodeBench 自带的判题程序会误判：它模拟的 `sys.stdin.buffer.readline` 每次都返回输入的第一行，也不支持 `sys.stdout.buffer`，`abc397_d` 的第 41 个测试标准答案错误，`arc195_c` 允许任意合法构造却按单一答案比对。`cb rejudge` 把每份 AtCoder 答案作为独立进程运行（每个测试 6 秒），这两题用校验器，LeetCode 题沿用 LCB 判分；结果写到运行目录的 `rejudge.jsonl`，并打印复核前后的 pass@1。对比模型时用复核后的结果。

每次评测都要输出静态代码质量（`cb livecodebench` 跑完会自动运行 `cb quality`），按 Huang 等人的 *Beyond Functional Correctness: Static Code Quality Profiling of LLM-Generated Code*（arXiv:2610.19167）的口径输出静态代码质量：
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
- `STREAM`：默认 1，LiveCodeBench 和 CRUXEval 都用流式请求：卡住的请求很快超时重试，记录首个 token 和首个回答 token 的时间，`cb progress` 能看到进行中的请求（运行目录里的 `usage.jsonl.live.<进程号>` 每 10 秒更新一次）。流没有结束标记就断开时，收到的半截回答不算数，按出错重试。端点不支持 `stream_options` 时自动去掉这个字段再请求。设成 0 就一次取回整个回答。BigCodeBench 用它自带的请求方式，不受影响。旧名 `LCB_STREAM` 仍然有效。
- `LCB_TIMEOUT`：流式时是“多久收不到新 token 就重试”，默认 300 秒；`STREAM=0` 时是整个回答最多等多久，默认 1800 秒。
- `LCB_OMIT`：LiveCodeBench 请求里不发送的字段，逗号分隔。有的模型把这些参数固定了，发了会报错，比如 Kimi K3.1 Pro 要设 `LCB_OMIT=temperature,top_p,n,presence_penalty,frequency_penalty`（它固定 temperature 1.0、top_p 0.95）。
- `CB_POST`：默认 1，LiveCodeBench 跑完自动做后处理（见上）；设成 0 跳过。
- `PRICE_IN`、`PRICE_HIT`、`PRICE_OUT`：每百万 token 的单价（输入未命中缓存 / 命中缓存 / 输出，思考算输出），`cb usage` 用来算费用；不设就不算。分时计价的平台再设 `PRICE_OFF_IN`、`PRICE_OFF_HIT`、`PRICE_OFF_OUT`（非高峰单价）和 `PEAK_HOURS_UTC`（工作日的高峰时段，UTC，默认 DeepSeek 的 `1-4,6-10`），每次调用按开始时间计价。
- `SONAR_URL`、`SONAR_TOKEN`、`SONAR_SCANNER`：`cb quality --sonar` 用的本机 SonarQube 地址、令牌和扫描器路径（`deploy/sonarqube.sh start` 生成）。
- `CRUX_MAX_TOKENS`：CRUXEval 官方每次回答只给 100 个 token（带思维链的模式是 1000），那是给普通模型定的。推理模型的思考也算在 token 数里，会被截断成空答案，所以推理模型要设成和 `MAX_TOKENS` 一样。

结果在 `runs/<模型名>/<benchmark>-full/result.json`，模型的原始回答也在同一个目录里；LiveCodeBench 另有 `problems.json`（本次的题目清单）和 `usage.jsonl`（每次 API 调用一行：题号、起止时间、首个 token 时间、token 用量、结束原因、回答或错误）。某题的请求重试次数用完、或账户余额不足时，这题记为空答案（判为失败），其余题照常保存和打分；余额不足后不再发新请求。中途断了直接重跑同一条命令：已经答过的题不会再请求一次（每次都会把已有的回答重新判一遍分，在本机跑，不花钱）。


## 阶梯测试集（cb ladder）

现有的 LiveCodeBench 题已经被最强的模型做满，所以另建一套按难度分档、带官方测试数据的题：

| 档 | 来源 | 作答语言 | 计分 |
|---|---|---|---|
| L1 基础 | USACO 2024-25、2025-26 赛季铜组（21 题） | Python | 每个测试点等分 |
| L2 中等 | USACO 银组（21 题） | Python | 每个测试点等分 |
| L3 困难 | USACO 金组（21 题）+ EGOI 2026（6 题；另 2 道交互题暂不支持） | C++ | USACO 按测试点；EGOI 按子任务（子任务内取最低） |
| L4 顶尖 | USACO 铂金组（21 题）+ IOI 2026（批处理题） | C++ | USACO 按测试点；IOI 按子任务 |
| L5 开放式 | FrontierCS 算法赛道（固定抽 30 题，按题号均匀取；题库没有类别标签） | C++17 | 官方 checker 给 0–100 的连续分（达到参考解 60 分，超过有对数加分） |

- 题目、测试数据和官方题解全部来自官方发布（USACO 官网、egoi-org/egoi-2026、ioi/task-archive、FrontierCS 仓库），钉在固定的 commit；下载清单是 `samples/ladder_download.tsv.gz`，由 `tools/ladder_sources.py` 生成。AtCoder 从 2024-12 起不再公开测试数据，LeetCode 测试不公开，所以没有用。
- 判题在本机进行，不用 Docker：答案以 `bench` 用户运行，经一个小的 `python -I -S` 启动器设置内存、栈、CPU、输出大小上限并绑核，CPU 时间和峰值内存取自子进程的 rusage。每个测试点只跑一次，时限放宽到官方的 `LADDER_LENIENT` 倍（默认 5 倍）；按 CPU 时间同时得出“宽时限”（算法对不对）和“官方时限”（够不够快）两种判定。USACO 按空白分隔的 token 比对，EGOI/IOI 用官方 checker 和 grader，FrontierCS 用官方 testlib checker/interactor（规则照搬它的 judge_engine.js）。
- 建库时（`cb ladder-build --calibrate`）先把每题的所有官方题解在全部测试上判一遍：没有一份官方解能通过的题不进清单；通过的官方解里最快的一份作为性能对照。
- 代码性能：解出的答案在官方解最慢的 3 个测试点上和官方解交替各跑 3 次取中位数，报告“答案 CPU 时间 ÷ 官方解”的几何平均。
- 时间与空间复杂度：每份解出的答案在官方测试上按输入大小拟合增长幂次 k（log CPU 时间或峰值内存对 log 输入字节数的斜率，扣除空程序的开销），与官方解在同一批测试点上比：增长慢于官方解（Δk ≤ −0.3）为“更优”，可能是更好或更新颖的解法，报告里单独列出供人工复核；|Δk| < 0.3 为“相同”；Δk ≥ 0.3 为“更差”（即使通过了时限）。输入大小变化不足 8 倍或可测测试点少于 4 个的题记为不可测（`tools/ladder_complexity.py`，写 `complexity.jsonl`）。
- 静态质量：L1–L2 的 Python 答案按 arXiv:2610.19167 的口径（同 `cb quality`）；C++ 档位不做（这些工具只支持 Python，SonarQube 10.4 社区版不分析 C/C++）。
- 2026 子集（EGOI、IOI）和同档的 USACO 题分开报告：难度相当而新题明显更差时，旧题成绩可能受训练数据泄露影响。

```bash
cb ladder-data              # 后台下载题目数据（可断点续传，约 4.7 GB）；cb ladder-data --status 看进度
cb ladder-fetch             # 网络快的机器上用这个：并行下载并逐个校验（git sha1、zip CRC），--verify 只校验
cb ladder-build             # 把下载的数据整理成题目；再 cb ladder-build --calibrate 判官方解、选性能对照
cb ladder-build --manifest $CB/data/ladder/ladder.json   # 写出题目清单（只有编号、档位、日期、时限）；核对后复制成仓库里的 samples/ladder.json
export MODEL=... OPENAI_BASE_URL=... OPENAI_API_KEY=...
cb ladder --smoke           # 每档只跑第一题，先确认接口和格式
cb ladder                   # 全量：生成 → 判题 → 性能复测 → 复杂度 → 静态质量 → 报告（runs/<模型>/ladder-full/report/）
cb progress <模型>/ladder-full --watch 30         # 跑的过程中看进度（同 LiveCodeBench）
cb ladder-report <运行A> <运行B> --out <目录>     # 多个模型放在一份报告里对比；有 xelatex 就直接出 PDF
```

**在 Windows 工作站上运行（WSL2）**：判题要用 Linux 的进程和资源限制，所以在 Windows 上用 WSL2 的 Ubuntu（x86 机器即可，不需要 GPU）。在 PowerShell 里 `wsl --install -d Ubuntu`，重启后进入 Ubuntu：

```bash
git clone git@github.com:BAI-AI-Lab/codingBench.git && cd codingBench   # 先在 WSL 里配好 GitHub 的 SSH key
sudo bash deploy/wsl_setup.sh                                  # 装编译器和两个 Python 环境，下载并校验题目数据，建库，判官方解
# 数据已经在 U 盘/移动硬盘上（tools/ladder_fetch.py 下载过）：sudo bash deploy/wsl_setup.sh --data /mnt/e/codingBench_ladder/raw
export MODEL=deepseek-flash OPENAI_BASE_URL=https://api.deepseek.com/v1 OPENAI_API_KEY=sk-...
cb ladder --smoke && cb ladder                                 # 报告在 /opt/code_bench/runs/<模型>/ladder-full/report/
```

安装目录默认是 `/opt/code_bench`（`CB=... sudo -E bash deploy/wsl_setup.sh` 可改），布局和实验室服务器相同：脚本归 root，模型写的代码以无权限用户 `bench` 运行。注意 WSL 默认把 Windows 磁盘挂在 `/mnt/c` 等处，`bench` 用户能读到上面的文件；不放心的话在 `/etc/wsl.conf` 里关掉 automount。PyPI 用默认源（`$CB/mirrors` 写的是 `global`）。报告的 PDF 需要 `sudo apt install texlive-xetex texlive-lang-chinese`，排版会直接用 Windows 自带的 Times New Roman 和楷体（`/mnt/c/Windows/Fonts`）；也可以把报告目录拷到 Mac 上运行 `bash build.sh`。SonarQube 需要 Docker（Docker Desktop 打开 WSL 集成后可用 `deploy/sonarqube.sh start`，用 `SONAR_DIR` 指定数据目录）；不开就只出 Pylint 和 Radon。

可选的环境变量：`LADDER_N`（每档采样次数，默认 `L1=1,L2=1,L3=3,L4=3,L5=1`）、`MAX_TOKENS`（默认不设上限）、`WORKERS`、`STREAM`、`LADDER_TIMEOUT`（同 `LCB_TIMEOUT`）、`LADDER_OMIT`（同 `LCB_OMIT`）、`TEMPERATURE`（默认 0.2）、`LADDER_LENIENT`、`LADDER_CORES`（判题用的核数，默认 64）、`PRICE_*`（算费用）。中途断了直接重跑同一条命令，已经答过的不再请求。报告的 PDF 用 Times New Roman 和楷体排版，服务器上没有 xelatex 和这两种字体，把报告目录拷到 Mac 上运行 `bash build.sh` 即可。`tests/test_ladder.py` 用合成题和 `tests/mock_openai.py`（假的模型接口，回答官方解）把整条管路测一遍，CI 里也跑。


## 打分口径

- 都是 pass@1。BigCodeBench 用贪心解码（temperature 0），LiveCodeBench 和 CRUXEval 用 temperature 0.2、每题 1 次。
- 和官方排行榜的提示词、打分程序相同。CRUXEval 官方排行榜每题采样 10 次再算 pass@1，这里每题 1 次，所以单次结果会有几个点的波动。


## 目录

- `bin/cb`：入口；`bin/lcb_run.py`、`bin/crux_run.py`：在官方代码外面套的一层（不改官方代码）
- `tools/lcb_quality.py`：静态代码质量（`cb quality`）；`deploy/sonarqube.sh`：本机 SonarQube
- `tools/lcb_progress.py`：运行中的进度（`cb progress`）；`tools/lcb_rejudge.py`：复核判分（`cb rejudge`）；`tools/lcb_perf.py`：代码性能（`cb perf`）；`tools/lcb_report.py`：LiveCodeBench 报告；`tools/lcb_usage.py`：延迟和 token 报告（读 LiveCodeBench 运行目录里的 `usage.jsonl`）
- `samples/`：固定的题目清单；`samples/ladder.json`、`samples/ladder_download.tsv.gz`：阶梯测试集的题目清单和下载清单
- `bin/ladder_run.py`、`tools/ladder_*.py`：阶梯测试集的生成、建库、判题、静态质量和报告；`tests/test_ladder.py`、`tests/mock_openai.py`：它的测试
- `deploy/setup.sh`：安装和更新（只在仓库里）
- `reports/`：跑过的评测报告（`2026-10-23_lcb35_kimi_deepseek`：LiveCodeBench 最新 35 题；`2026-10-27_ladder_design`：阶梯测试集的设计说明；`2026-10-28_ladder_deepseek-flash`：阶梯测试集的第一轮评测）
- 结果网站：https://bai-ai-lab.github.io/coding-eval/（公开仓库 `BAI-AI-Lab/coding-eval`）。由 `reports/2026-10-23_lcb35_kimi_deepseek/site.py` 生成：在放好 `runs/` 的报告目录里运行 `python site.py <coding-eval 的检出目录>`（需要 pygments），然后在该目录提交并推送
- `SURVEY.md`：选这几个 benchmark 时调研过的约 45 个代码 benchmark（会议、获奖级别、怎么跑、国内能不能下）
- `src/`：三个官方仓库（`install.sh` 拉取，钉在测过的 commit 上）
- `venvs/`：每个 benchmark 一个独立的 Python 环境
- `data/code_generation_lite/`：LiveCodeBench 的题目（从 OpenCompass 的阿里云镜像下载，sha256 和 HF 官方一致）
- `data/ladder/`：阶梯测试集的原始下载（`raw/`）和整理好的题目（`problems/`，题面和测试数据只在服务器上，不进仓库）
- `runs/`：结果

## 许可证

代码以 MIT 许可证发布（见 `LICENSE`）。评测用的题目、测试数据和官方题解不在仓库里，下载自各自的官方来源，版权归原作者所有：USACO、EGOI 2026、IOI 2026（CC BY 4.0）、FrontierCS（MIT）。
