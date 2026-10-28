# 阶梯代码评测集（ladder-v1，2026-10-27）

一句话：按人类难度分 5 档的竞赛编程题，测模型写的代码**做没做对、够不够快、复杂度如何、代码质量怎样**。所有题目、测试数据和官方题解都来自官方发布，判题规则与官方一致。设计原理见 `reports/2026-10-27_ladder_design/report.pdf`，第一轮结果（只含 USACO 65 题）见 `reports/2026-10-28_ladder_deepseek-flash/report.pdf`，完整一轮（L1–L5 共 112 题）见 `reports/2026-10-29_ladder_deepseek-flash/report.pdf`。

| 档 | 题目来源 | 题数 | 作答语言 | 计分 |
|---|---|---:|---|---|
| L1 基础 | USACO 2024-25、2025-26 铜组 | 21 | Python 3 | 测试点等分 |
| L2 中等 | USACO 银组 | 21 | Python 3 | 测试点等分 |
| L3 困难 | USACO 金组 + EGOI 2026 | 21 + 6 | C++17 | 测试点 / 子任务（取最低） |
| L4 顶尖 | USACO 铂金组 + IOI 2026 批处理题 | 21 + 2 | C++17 | 测试点 / 子任务（取最低） |
| L5 开放式 | FrontierCS 算法赛道（按题号均匀抽 30 题，题库 180） | 30 | C++17 | 官方 checker 给 0–100 连续分 |

题数是计划数：建库时，没有任何官方题解能通过的题，以及有多个合法答案却没有 checker 的题，会被剔除，最终以 `data/ladder/ladder.json` 为准。

## 一、要装什么

| 东西 | 说明 |
|---|---|
| 系统 | Linux x86_64（Ubuntu 22.04 及以上），或 Windows 上的 **WSL2 Ubuntu**。macOS 不行：ARM 架构下 `#pragma GCC target("avx2")` 等会编译失败，而且不强制内存上限、不能绑核 |
| 系统软件 | `g++`、`python3`、`curl`、`git`、`rsync`（安装脚本会用 apt 自动装） |
| Python 环境 | `venvs/ladder`（Python 3.12，openai、httpx、PyYAML：生成、判题、报告）和 `venvs/quality`（Pylint 3.3.5、Radon 6.0.1：静态质量），由 `install.sh --ladder` 用 uv 自动装 |
| 题目数据 | 4 份，共 17163 个文件、约 4.75 GB，全部列在 `samples/ladder_download.tsv.gz`，带官方哈希：USACO 两个赛季（usaco.org，1.59 GB）、EGOI 2026（github egoi-org/egoi-2026 @ 08eedd3，0.52 GB）、IOI 2026（github ioi/task-archive @ 70278df，0.46 GB）、FrontierCS 算法赛道（github FrontierCS/Frontier-CS @ 12ab268，2.18 GB）。安装脚本自动下载并逐个校验（git sha1、zip CRC） |
| 磁盘 | 约 10 GB（原始数据 + 建好的题库） |
| 模型 API | 任意 OpenAI 兼容接口：`MODEL`、`OPENAI_BASE_URL`、`OPENAI_API_KEY` |
| 可选：SonarQube 10.4 | 静态质量里的 SonarQube 一项，需要 Docker（`deploy/sonarqube.sh start`）；不装就只出 Pylint 和 Radon |
| 可选：PDF 报告 | `sudo apt install texlive-xetex texlive-lang-chinese`；字体用 Times New Roman 和楷体（WSL 下自动使用 Windows 自带字体） |

不需要 GPU。

## 二、怎么跑

**1. 一次性安装**（在仓库检出目录里，用有 sudo 权限的用户）：

```bash
git clone git@github.com:BAI-AI-Lab/codingBench.git && cd codingBench
sudo bash deploy/wsl_setup.sh                                     # 装软件和环境、下载并校验数据、建库、判官方解
# 数据已经在别的盘上（tools/ladder_fetch.py 下载过）就直接复制：
# sudo bash deploy/wsl_setup.sh --data /mnt/e/codingBench_ladder/raw
```

装到 `/opt/code_bench`（`CB=/别的目录 sudo -E bash deploy/wsl_setup.sh` 可改）。模型写的代码以无权限用户 `bench` 运行，脚本本身归 root，模型代码改不了评测程序。最后一行出现 `READY` 就是装好了。

**2. 接上模型，先冒烟、再全量：**

```bash
export MODEL=deepseek-flash OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=sk-...
export MODEL_NAME="DeepSeek Flash V4.1-1017"                # 报告标题里写的模型全名（不设就用 MODEL）
export PRICE_IN=0.3 PRICE_HIT=0.006 PRICE_OUT=1.2          # 可选：每百万 token 单价（美元），报告里算费用
cb ladder --smoke                                          # 每档只跑第一题、采样 1 次，确认接口和格式（几分钟）
cb ladder                                                  # 全量：生成 → 判题 → 性能复测 → 复杂度 → 静态质量 → 报告
```

常用选项：

| 选项 | 作用 |
|---|---|
| `cb ladder --tiers L1,L2` | 只跑某几档 |
| `cb ladder --only usaco-1443,fcs-0` | 只跑某几题 |
| `LADDER_N=L1=1,L2=1,L3=3,L4=3,L5=1` | 每档采样次数（这是默认值） |
| `WORKERS=8` | 同时发出的请求数，默认 16。平台限并发（DeepSeek 余额低时只给 5–7 路）就调小 |
| `MAX_TOKENS=262144` | 每次回答的最大 token 数，默认不传上限。推理模型做难题经常思考 10 万 token 以上 |
| `LADDER_OMIT=temperature,top_p` | 请求里不发送的字段（有的模型固定了这些参数，发了会报错，例如 Kimi） |
| `LADDER_CORES=16` | 判题用的 CPU 核数，默认最多 64 |
| `CB_POST=0` | 只生成不做后处理，之后用 `cb ladder-post <运行目录>` 补 |

**3. 想暂停**：`touch /opt/code_bench/runs/<模型名>/ladder-full/STOP`，已经发出的请求会答完再停（不浪费已付费的生成），之后重跑同一条命令继续。

**4. 中途断了直接重跑同一条命令**：已经拿到回答的采样不会再请求（不重复花钱）；因为接口错误、重试用完没拿到回答的采样会重新请求。

**5. 跑的过程中看进度**：`cb progress <模型名>/ladder-full --watch 30`，可以看到已答数、出错数、每个进行中请求的耗时，以及已经收到的思考和回答字数。

## 三、怎么看结果

结果在 `/opt/code_bench/runs/<模型名>/ladder-full/`：

| 文件 | 内容 |
|---|---|
| `report/report.md` | **报告正文**（Markdown，直接看） |
| `report/main.tex`、`report/build.sh` | 同一份报告的 LaTeX；`bash build.sh` 出 PDF |
| `report/report.json` | 报告里所有数字的机器可读版 |
| `answers.jsonl` | 每个采样提取出的代码 |
| `judge.jsonl` | 每份答案每个测试点的判定、得分、CPU 时间、峰值内存 |
| `perf.jsonl`、`complexity.jsonl` | 性能复测与复杂度测量的原始数据 |
| `quality.jsonl` | Python 答案的 Pylint / Radon / SonarQube 结果 |
| `usage.jsonl`、`problems.json`、`run.json` | 每次 API 调用的记录、本次题单、运行参数 |

报告的结构和读法：

1. **评测维度与打分标准**：一张表写明每个指标怎么算、方向如何（↑ 越大越好，↓ 越小越好）。各维度分开报告，**不合成总分**。
2. **各档正确率**：
   - **pass@1（宽时限）**：时限放宽到官方的 5 倍，看算法对不对；
   - **pass@1（官方时限）**：看是否和人类选手一样在时限内通过；
   - **平均得分**：含部分分，USACO 按测试点，EGOI/IOI 按子任务，FrontierCS 按 0–100；
   - **pass@n**：L3、L4 每题 3 次采样里至少对一次的比例。
   - 宽时限和官方时限差得多，说明模型常写出思路对但复杂度偏高的解法。
3. **2026 新题与 USACO 对照**：同档内 EGOI/IOI 2026 新题和 USACO 旧题分开列。新题明显更差时，提示旧题可能出现在训练数据里，只作提示，不作结论。
4. **代码性能**：答案 CPU 时间 ÷ 官方解，在官方解最重的 3 个测试点上和官方解交替测量，取几何平均。小于 1 表示比官方解快。
5. **时间与空间复杂度**：答案耗时（或内存）相对官方解的增长幂次 k。
   - 斜率拟合度 R² ≥ 0.8 时下结论：k ≤ 0.75 且在官方解最重的测试点上至少快 2 倍为**更优**；0.75–1.33 为**同阶**；k ≥ 1.33 且至少慢 2 倍为**更差**；其余为**不确定**。
   - 更优的答案会单独列出，值得人工看一看是不是更好或更新颖的解法。
6. **失败类型**：每份没解出的答案的主要原因，包括无代码、编译错误、答案错误、部分分、运行错误、超内存、超时、只在官方时限下超时。
7. **静态质量**（仅 L1–L2 的 Python 答案）：按 arXiv:2610.19167 的口径，包括 Pylint 问题数和得分、圈复杂度、可维护性指数、SLOC、SonarQube 三类问题数。
8. **用量与费用**：有效调用数、输出 token、延迟中位数、费用。
9. **逐题结果**：每题解出几次、平均得分、主要失败原因。

**多个模型放在一份报告里对比**：

```bash
cb ladder-report /opt/code_bench/runs/模型A/ladder-full /opt/code_bench/runs/模型B/ladder-full --out ~/ladder_compare
```

注意：「官方时限」「性能」「复杂度」都和机器有关。要对比的模型必须在**同一台机器**上判题；在不同机器上跑的结果只能比正确率。

## 四、这一版的已知限制

- **EGOI 2026 少 2 题**：Census 和 Seating Plan 是交互题（官方管理程序或控制程序与选手程序对话），判题程序还不支持，建库时跳过，EGOI 实际 6 题。
- **IOI 2026 不全**：6 题里 4 题是通信题（管理程序加多个选手进程），判题程序还不支持；另外 2 道批处理题的英文题面只有 PDF，还没转成文本。所以这一版里 IOI 题会在建库时被跳过，L4 暂时只有 USACO 铂金组。
- **EGOI 和 FrontierCS 没有官方题解**：两者都没有公开题解，所以这两部分没有性能和复杂度对照，报告里记为“无官方解”。正确性用官方 checker 和标准答案判定；建库时会先做 checker 自检：EGOI 要求标准答案得满分、空输出得 0 分，FrontierCS 要求 checker 能正常结束、空输出不得分。
- **FrontierCS 判题程序未核对**：本机判题照搬官方的判分规则，但还没有和它公开排行榜上的分数逐题核对。
- **复杂度靠官方测试估算**：官方测试不是按规模排列的序列（USACO 里耗时长的测试点大多都是最大规模），所以以官方解的工作量为横轴估算增长阶，能下结论的约占一半。下一版会用 EGOI 的官方生成器（USACO 另写）造出不同规模的输入来测。
- **C++ 档没有静态质量**：Pylint 和 Radon 只支持 Python，SonarQube 10.4 社区版不分析 C/C++。
- **AlgoTune 性能专项**（把数值程序写快）还没有接入。
