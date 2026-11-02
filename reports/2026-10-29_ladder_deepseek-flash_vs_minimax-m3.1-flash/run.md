# 运行说明：2026-10-29 阶梯评测

本文说明本目录报告（`report.pdf` / `report.md`，DeepSeek Flash V4.1-1017 与 MiniMax M3.1 Flash）的题目怎么选、怎么判题、怎么运行。DeepSeek 的结果与 [`../2026-10-29_ladder_deepseek-flash/`](../2026-10-29_ladder_deepseek-flash/) 来自同一次运行，逐题得分相同。

用到的代码都在本仓库：选题与建库 `tools/ladder_sources.py`、`tools/ladder_build.py`；生成 `bin/ladder_run.py`；判题 `tools/ladder_judge.py`、`tools/ladder_lib.py`；复杂度 `tools/ladder_complexity.py`；静态质量 `tools/ladder_quality.py`；报告 `tools/ladder_report.py`。入口是 `bin/cb`。

## 一、题目怎么选的

### 原则

- **只用带官方测试数据的竞赛题**，这样能在本地准确判出对错和用时。AtCoder 从 2024-12 起不再公开测试数据，LeetCode 的测试不公开，所以都不用。
- **难度按比赛自己的分组分档**，不靠人工打分：USACO 的铜、银、金、铂金组依次是 L1–L4。
- **加入 2026 年的新题**（EGOI 2026、IOI 2026），和同档的 USACO 旧题分开报告，用来检查训练数据泄露。
- **L5 用 FrontierCS 算法赛道**：开放式优化题，没有唯一的标准答案，官方 checker 给 0–100 的连续分，用来拉开强模型之间的差距。
- **来源钉在固定版本**：
  - USACO 官网 2024-25 赛季的 4 场（2024-12、2025-01、2025-02、2025 US Open）和 2025-26 赛季的 3 场，每场每组 3 题；
  - egoi-org/egoi-2026 @ `08eedd3`；
  - ioi/task-archive @ `70278df`（`2026/` 目录）；
  - FrontierCS/Frontier-CS @ `12ab268`。

  下载清单 `samples/ladder_download.tsv.gz` 记录了每个文件的地址、大小和 git sha1，`tools/ladder_sources.py` 可以重新生成它。题面和测试数据不放进本仓库，运行时从官方来源下载。

### 校准：先用官方题解检验每道题

建库之后、写题单之前，先运行 `cb ladder-build --calibrate`：

- **有官方题解的题（USACO）**：每份官方题解都在全部官方测试上判一遍，时限取官方时限的 2 倍。
  - 一份都通不过的题不进题单。
  - 能通过的题解里，最快的一份作为代码性能和复杂度的对照。
- **没有官方题解的题**：改为检验 checker。
  - EGOI：官方 checker 必须给官方答案满分，给空输出 0 分。
  - FrontierCS：checker 必须能编译、返回 testlib 的退出码，并给空输出 0 分。

### 入选结果

| 档 | 来源 | 候选 | 入选 | 未入选的题及原因 | 作答语言 | 每题采样 |
|---|---|---:|---:|---|---|---:|
| L1 基础 | USACO 铜组 | 21 | 18 | usaco-1540、usaco-1589：没有官方题解能通过全部测试；usaco-1563：答案不唯一，没有 checker | Python | 1 |
| L2 中等 | USACO 银组 | 21 | 19 | usaco-1518、usaco-1566：没有官方题解能通过全部测试 | Python | 1 |
| L3 困难 | USACO 金组 + EGOI 2026 | 21 + 8 | 21 + 6 | egoi26-census、egoi26-seatingplan：交互题，需要官方的 manager / controller 程序，现在的判题程序不支持 | C++ | 3 |
| L4 顶尖 | USACO 铂金组 + IOI 2026 | 21 + 6 | 18 + 0 | usaco-1597、usaco-1598：没有官方题解能通过全部测试；usaco-1524：答案不唯一，没有 checker；IOI 2026 的 ballmachine、tiling、classroom、partition 是通信题（Communication），不支持；monuments、magiccity 的题面只有 PDF，还没有转成文本 | C++ | 3 |
| L5 开放式 | FrontierCS 算法赛道 | 180 | 30 | 题库没有类别标签，按题号排序后每 6 题取 1 题（第 1、7、13……题） | C++17 | 1 |
| 合计 | | | 112 | | | 202 个采样 |

两道 EGOI 交互题在 DeepSeek 运行时还在题单里。DeepSeek 对它们的 6 个答案不计入成绩，在用量表里单列为“已剔除的题”。MiniMax 运行时这两题已经不在题单里。

<details>
<summary>112 道题的编号</summary>

- **L1（18）**：usaco-1443 1444 1445 1467 1468 1469 1491 1492 1493 1515 1516 1517 1539 1541 1564 1565 1587 1588
- **L2（19）**：usaco-1446 1447 1448 1470 1471 1472 1494 1495 1496 1519 1520 1542 1543 1544 1567 1568 1590 1591 1592
- **L3（27）**：
  - usaco-1449 1450 1451 1473 1474 1475 1497 1498 1499 1521 1522 1523 1545 1546 1547 1569 1570 1571 1593 1594 1595
  - egoi26-biscuits cakes ferriswheel foxfamilies ovenmasters wateringplants
- **L4（18）**：usaco-1452 1453 1454 1476 1477 1478 1500 1501 1502 1525 1526 1548 1549 1550 1572 1573 1574 1596
- **L5（30）**：fcs-0 6 13 23 30 42 48 58 68 77 85 104 111 121 132 141 148 154 160 166 174 183 193 211 222 239 249 257 304 310

</details>

## 二、怎么测试的

### 提示词与答案提取

- **USACO、EGOI 的提示词**沿用 LiveCodeBench 的写法：系统提示，加上题面，加一行时空限制，再要求代码从标准输入读、向标准输出写，并放进 ` ```python ` 或 ` ```cpp ` 代码块。
  - 时空限制那一行形如 `Time limit: <官方时限> seconds per test. Memory limit: <内存> MB.`。
  - 句末，Python 档写 `Python 3 standard library only.`，C++ 档写 `Compiled with g++ -O2 -std=gnu++17.`。
- **FrontierCS** 用它官方发布的提示词，这样分数和它的排行榜可比。
- **每个采样是一次独立请求**：单轮对话，没有工具，也不给测试反馈。
- **答案提取**：取回答里最后一个对应语言的代码块（LiveCodeBench 的规则）；没有代码块的记“无代码”。

### 运行与限制

- **判题环境**：在 Linux x86-64 上直接判题，不用 Docker。模型写的程序以无权限用户 `bench` 运行。
- **资源限制**：程序经一个 `python -I -S` 启动器运行，启动器设置以下限制：
  - CPU 时间：官方时限的 5 倍（宽时限）；
  - 地址空间：官方内存限制加 64 MB；栈：官方内存限制；
  - 输出：最多 256 MB；
  - 墙钟时间超过宽时限的 2 倍加 1 秒，强制结束。
- **测量**：每个测试点绑定一个 CPU 核，多个测试点并行运行。CPU 时间和峰值内存取自子进程的 rusage。
- **编译与解释器**：C++ 用 `g++ -O2 -pipe -std=gnu++17`；Python 用 3.12，只能用标准库，以 `python -I -S -B` 运行。
- **两种时限的判定**：每个测试点只运行一次，同时得出两种判定。
  - 宽时限：5 倍官方时限内对不对，看算法是否正确。
  - 官方时限：CPU 时间是否没超过官方时限，看是否和人类选手一样在时限内通过。

### 计分

- **USACO**：忽略空白，逐 token 比对；各测试点等分，满分 100。
- **EGOI**：官方 checker 给每个测试点 0–1 分；每个子任务取其中测试点的最低分，再乘以子任务分值。
- **FrontierCS**：用官方的 testlib checker / interactor，规则照搬它的 `judge_engine.js`；题目得分是各测试点 Ratio 的平均（达到参考解为 60 分，超过参考解按对数加分）。
- **解出**：所有测试点都拿满分。
- **其余指标**：pass@1、平均得分、pass@3，以及代码性能、复杂度、失败类型、静态质量、用量与费用、泄露检查的具体规则，见报告的“评测维度与打分标准”一节。

### 判题之后（`cb ladder-post`）

- **代码性能**：解出的答案在官方解最慢的 3 个测试点上，和官方解交替各运行 3 次，取中位数。
- **复杂度**：在官方解耗时至少 2 ms 的测试点上（最多 20 个），答案和官方解交替各运行 5 次，拟合答案相对官方解的增长幂次。
- **静态质量**：L1–L2 的 Python 答案跑 Pylint 3.3.5 和 Radon 6.0.1。SonarQube 需要 Docker，这台机器上没有，未测。

## 三、怎么运行的

**机器**：一台 Linux x86-64 云主机，16 个 CPU 核，62 GB 内存。生成和判题都在这台机器上，两个模型的答案用同一套判题程序和设置。官方时限下的结果对机器负载敏感：可用的核比并行的测试点少时，判出的“超时”会明显变多。复现时应让每个测试点独占一个核。宽时限留了 5 倍余量，基本不受影响。

| 项目 | DeepSeek Flash V4.1-1017 | MiniMax M3.1 Flash |
|---|---|---|
| API 模型名 | `deepseek-flash` | `MiniMax-M3.1-Flash` |
| 接口 | DeepSeek 官方 API | MiniMax 官方 API（国内站，OpenAI 兼容）；分两个账户（Token Plan 套餐与按量计费）完成，模型和参数相同 |
| 运行日期（北京时间） | 2026-10-28 至 10-29 | 2026-10-29 |
| temperature / top_p | 请求里是 0.2 / 0.95，但思考模式下 DeepSeek 忽略 temperature，实际用它的默认采样 | 0.2 / 0.95 |
| max_tokens | 262144 | 262144 |
| 思考深度（reasoning_effort） | 未设置，用接口默认的 high（官方评测用 max） | 未设置，用接口默认的 max |
| 并发请求 | 8 | 8 |
| 流式输出 | 是 | 是 |
| 单次生成时限 | 未设置；最长的一次调用 884 秒，没有超过 20 分钟的 | 20 分钟。超时的 13 个采样以 30 分钟为限重问一次：3 个完成，10 个记“生成超时”（按失败计；其中 6 个是服务端在约 24–30 分钟时断开） |
| 计价（每百万 token：输入 / 缓存命中 / 输出） | $0.30 / $0.006 / $1.20；北京时间非高峰时段半价，按每次调用的开始时间计 | $0.15 / $0.015 / $0.60 |
| 调用数 / 采样数 | 208 / 202（多出的 6 次是已剔除的 2 道 EGOI 题） | 215 / 202（多出的 13 次是超时后的重问） |

两个模型的调用参数不完全对等：思考深度不同，DeepSeek 实际也没有用 0.2 的 temperature。技术报告（`paper/main.pdf`）的局限一节讨论了这一点。

运行中断后重跑同一条命令即可：已有答案的采样不再请求，接口报错的采样会重问。两个模型最终都是 202 个采样全部有结果。

### 命令

在 Ubuntu（x86-64）上执行：

```bash
# 1. 安装和建库，一次即可（任意 x86-64 Linux，或 Windows 的 WSL2）：建 bench 用户，装编译器和两个 Python 环境，
#    下载并校验题目数据（cb ladder-fetch），建库（cb ladder-build），用官方题解校准（--calibrate），
#    写出题单（--manifest $CB/data/ladder/ladder.json）
sudo bash deploy/wsl_setup.sh

# 每题采样数（LADDER_N）默认就是 L1=1,L2=1,L3=3,L4=3,L5=1，temperature 默认 0.2，下面不用再设

# 2. DeepSeek
export MODEL=deepseek-flash OPENAI_BASE_URL=https://api.deepseek.com/v1 OPENAI_API_KEY=<你的 key>
export WORKERS=8 MAX_TOKENS=262144
cb ladder --smoke && cb ladder        # 生成 → 判题 → 性能 → 复杂度 → 静态质量 → 单模型报告

# 3. MiniMax：另设单次生成时限 20 分钟，再把超时的采样以 30 分钟为限重问一次
export MODEL=MiniMax-M3.1-Flash OPENAI_BASE_URL=https://api.minimaxi.com/v1 OPENAI_API_KEY=<你的 key>   # Token Plan 账户用 https://api.minimax.cn/v1
export WORKERS=8 MAX_TOKENS=262144 LADDER_MAX_SECONDS=1200
cb ladder
LADDER_MAX_SECONDS=1800 LADDER_REDO_TIMEOUTS=1 LADDER_CUT_IS_TIMEOUT=1200 cb ladder
#   LADDER_CUT_IS_TIMEOUT=1200：运行超过 20 分钟后被服务端断开的请求也算生成超时，不重试

# 4. 对比报告：DeepSeek 用环境变量里的分时单价，MiniMax 用 --prices
PRICE_IN=0.30 PRICE_HIT=0.006 PRICE_OUT=1.20 PRICE_OFF_IN=0.15 PRICE_OFF_HIT=0.003 PRICE_OFF_OUT=0.60 \
cb ladder-report $CB/runs/deepseek-flash/ladder-full $CB/runs/MiniMax-M3.1-Flash/ladder-full \
  --prices "MiniMax-M3.1-Flash=0.15,0.015,0.60" --out <报告目录>
#   非高峰时段由 PEAK_HOURS_UTC 设定。PDF 需要 Times New Roman 和楷体，可把报告目录拷到 Mac 上运行 bash build.sh
```

运行过程中可以用 `cb progress <模型>/ladder-full --watch 30` 看进度。原始运行目录（`runs/<模型>/ladder-full/`，里面有每次调用的记录、答案和逐测试点的判题结果）不在仓库里；报告用到的全部数字都在本目录的 `report.json`。

由 Albert Huang 创建于 2026-11-01
