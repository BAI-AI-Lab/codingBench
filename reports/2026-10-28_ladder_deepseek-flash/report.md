# 阶梯代码评测报告（2026-10-28）

## 评测维度与打分标准

各维度分开报告，不合成总分；表格中 ↑ 越大越好，↓ 越小越好，没有箭头的只作描述。

| 维度 | 指标 | 计算方法 | 方向 |
|---|---|---|---|
| 正确性 | 测试点得分 s_t | 每个测试点 0–1：USACO 忽略空白逐 token 比对，相同为 1、否则 0；EGOI、IOI 取官方 checker 给出的 0–1 分；FrontierCS 取官方 checker 输出的 Ratio（达到参考解为 0.6，超过参考解按对数加分，最高 1）。程序编译失败、运行出错、超时或超内存，该测试点为 0。 |  |
| 正确性 | 题目得分 S（0–100） | USACO：S = 100 \cdot \frac{1}{T}\sum_t s_t（每个测试点等分）；EGOI、IOI：S = 100 \cdot \frac{\sum_g w_g \min_{t \in g} s_t}{\sum_g w_g}（子任务 g 取其中测试点的最低分，再乘以子任务分值 w_g）；FrontierCS：S = 100 \cdot \frac{1}{T}\sum_t \mathrm{Ratio}_t。 | ↑ |
| 正确性 | 解出 | 所有测试点 s_t = 1。 |  |
| 正确性 | pass@1、平均得分、pass@n | pass@1 = 解出的采样数 ÷ 采样总数 × 100；平均得分 = 所有采样的 S 的平均；pass@n = 至少一次采样解出的题数 ÷ 题数 × 100。每档采样次数：L1、L2、L5 各 1 次，L3、L4 各 3 次，temperature 0.2。 | ↑ |
| 正确性 / 效率 | 宽时限与官方时限 | 每个测试点只运行一次，时限为官方时限的 5 倍（宽时限）。宽时限口径：按上面的规则计分。官方时限口径：CPU 时间超过官方时限的测试点记 0，再按同样的规则算 S、pass@1。前者回答“算法对不对”，后者回答“是否和人类选手一样在时限内通过”。 | ↑ |
| 效率 | 运行时间倍数 | 只对解出的答案、且官方解在某个测试点上至少需要 0.05 秒 CPU 的题：取官方解最慢的 3 个测试点，答案与官方解交替各运行 3 次取中位数，r = 答案 CPU 时间 ÷ 官方解 CPU 时间（取官方解最慢的那个测试点）；各档报告 r 的几何平均和题数。同语言比较。 | ↓ |
| 效率 | 内存倍数 | 解出的答案在所有测试点上的峰值内存 ÷ 官方解的峰值内存，各档取几何平均。 | ↓ |
| 复杂度 | 相对官方解的增长幂次 k | 官方测试不是按规模排列的序列（USACO 里耗时较长的测试点大多都是最大规模），所以以官方解自己的工作量为横轴：在官方解至少需要 2 ms CPU（扣除空程序）的测试点上（最多 20 个，均匀覆盖其耗时范围），答案与官方解交替各运行 5 次取中位数，拟合 \log y_{答案} = a + k \log y_{官方}。若官方解为 \Theta(f(n))、答案为 \Theta(f(n)^k)，k 即该指数。R^2 \ge 0.8 时：k \le 0.75 且在官方解最重的 3 个测试点上答案至少快 2 倍为更优（列出供人工复核），0.75 < k < 1.33 为同阶，k \ge 1.33 且在这些测试点上至少慢 2 倍为更差；R^2 < 0.8，或斜率与最重测试点上的快慢对不上（某一方有固定开销会把斜率拉偏），为不确定；可用测试点少于 4 个或官方耗时跨度不足 4 倍为不可测。空间同理（峰值内存，至少高于空程序 1 MB）。这些测试点的输入大小跨度达到 8 倍时，另报两者按输入大小的增长幂次。 |  |
| 失败类型 | 每份未解出答案的主要原因 | 按顺序取第一个成立的：无代码、编译错误、答案错误、运行错误、超内存、超时、部分分（部分测试点得分）；宽时限下解出但官方时限下没有全部通过的记为“只在官方时限下超时”。 |  |
| 静态质量 | Pylint、Radon、SonarQube（只限 L1–L2 的 Python 答案） | 按 arXiv:2610.19167 的口径与版本：Pylint 3.3.5 默认配置的问题数（C/R/W/E）与 0–10 分，Radon 6.0.1 的圈复杂度（所有条目之和）、可维护性指数 MI、SLOC，SonarQube 10.4 的可维护性/可靠性/安全问题数；报告正确答案的每份平均与每百行 SLOC 的问题数。 | 见表头 |
| 成本与时延 | token、费用、延迟、首个 token 时间 | 费用 = (输入 − 缓存命中) × 输入单价 + 缓存命中 × 命中单价 + 输出（含思考）× 输出单价，单价按每百万 token，分时计价按每次调用的开始时间；延迟为每次调用从发出到收完的时间。 | ↓ |
| 泄露检查 | 2026 子集与 USACO 子集 | L3、L4 中 EGOI/IOI 2026 新题与同档 USACO 旧题分开报告 pass@1 与平均得分；新题明显更差时提示旧题可能见过。只作提示，不作结论。 |  |

## 各档正确率

| 档位 | 指标 | deepseek-flash |
|---|---|---:|
| L1 基础 | pass@1（宽时限）↑ | 100.0 |
| L1 基础 | pass@1（官方时限）↑ | 94.4 |
| L1 基础 | 平均得分（宽时限）↑ | 100.0 |
| L1 基础 | 平均得分（官方时限）↑ | 97.0 |
| L1 基础 | pass@n ↑ | 100.0 |
| L2 中等 | pass@1（宽时限）↑ | 94.7 |
| L2 中等 | pass@1（官方时限）↑ | 94.7 |
| L2 中等 | 平均得分（宽时限）↑ | 95.2 |
| L2 中等 | 平均得分（官方时限）↑ | 95.2 |
| L2 中等 | pass@n ↑ | 94.7 |
| L3 困难 | pass@1（宽时限）↑ | 96.7 |
| L3 困难 | pass@1（官方时限）↑ | 96.7 |
| L3 困难 | 平均得分（宽时限）↑ | 97.8 |
| L3 困难 | 平均得分（官方时限）↑ | 97.8 |
| L3 困难 | pass@n ↑ | 100.0 |
| L4 顶尖 | pass@1（宽时限）↑ | 70.8 |
| L4 顶尖 | pass@1（官方时限）↑ | 70.8 |
| L4 顶尖 | 平均得分（宽时限）↑ | 75.3 |
| L4 顶尖 | 平均得分（官方时限）↑ | 75.3 |
| L4 顶尖 | pass@n ↑ | 87.5 |

## 2026 新题与 USACO 对照（泄露检查）

本次评测还没有 2026 年的 EGOI/IOI 题，下表只是 USACO 两个赛季之间的对照（2025-26 赛季的题更新）。

| 档位 / 子集 | deepseek-flash |
|---|---:|
| L3 / USACO 2024-25（pass@1 / 得分）↑ | 97.2 / 98.9 |
| L3 / USACO 2025-26（pass@1 / 得分）↑ | 95.8 / 96.1 |
| L4 / USACO 2024-25（pass@1 / 得分）↑ | 70.8 / 75.3 |

## 代码性能（相对官方解，同语言）

| 档位 | deepseek-flash |
|---|---:|
| L1 基础：CPU 时间倍数（几何平均）↓ | 0.54×（11 份答案） |
| L2 中等：CPU 时间倍数（几何平均）↓ | 0.93×（7 份答案） |
| L3 困难：CPU 时间倍数（几何平均）↓ | 0.63×（52 份答案） |
| L4 顶尖：CPU 时间倍数（几何平均）↓ | 1.10×（14 份答案） |

## 时间与空间复杂度（相对官方解，同一批官方测试）

k = 答案耗时（或内存）相对官方解耗时（或内存）的增长幂次：k ≤ 0.75 且在官方解最重的测试点上至少快 2 倍为更优（可能是更好或更新颖的解法），0.75 < k < 1.33 同阶，k ≥ 1.33 且至少慢 2 倍为更差；其余为不确定。方法见上表“复杂度”一行。

| 档位 | 维度 | deepseek-flash |
|---|---|---:|
| L1 基础 | 时间 | 更优 1 / 同阶 8 / 更差 0 / 不确定 3 / 不可测 0 / 无官方解 6；k 中位数 0.93 |
| L1 基础 | 空间 | 更优 0 / 同阶 1 / 更差 0 / 不确定 2 / 不可测 9 / 无官方解 6；k 中位数 0.96 |
| L2 中等 | 时间 | 更优 1 / 同阶 7 / 更差 0 / 不确定 0 / 不可测 0 / 无官方解 10；k 中位数 0.95 |
| L2 中等 | 空间 | 更优 0 / 同阶 3 / 更差 0 / 不确定 0 / 不可测 5 / 无官方解 10；k 中位数 0.99 |
| L3 困难 | 时间 | 更优 5 / 同阶 29 / 更差 1 / 不确定 5 / 不可测 18 / 无官方解 0；k 中位数 0.99 |
| L3 困难 | 空间 | 更优 0 / 同阶 0 / 更差 0 / 不确定 9 / 不可测 49 / 无官方解 0；k 中位数 – |
| L4 顶尖 | 时间 | 更优 0 / 同阶 4 / 更差 0 / 不确定 1 / 不可测 9 / 无官方解 3；k 中位数 1.08 |
| L4 顶尖 | 空间 | 更优 0 / 同阶 1 / 更差 0 / 不确定 1 / 不可测 12 / 无官方解 3；k 中位数 1.30 |

- 增长慢于官方解、值得人工复核的答案：deepseek-flash usaco-1444#0（时间）；deepseek-flash usaco-1496#0（时间）；deepseek-flash usaco-1498#1（时间）；deepseek-flash usaco-1498#2（时间）；deepseek-flash usaco-1521#1（时间）；deepseek-flash usaco-1521#2（时间）；deepseek-flash usaco-1547#0（时间）

## 失败类型（答案数）

- deepseek-flash：L1 基础 只在官方时限下超时 1；L2 中等 答案错误 1；L3 困难 答案错误 2；L4 顶尖 无代码 1，编译错误 1，答案错误 4，运行错误 1

## 静态质量（L1–L2 Python，正确答案）

| 指标 | deepseek-flash |
|---|---:|
| Pylint 问题数 ↓ | 9.11 |
| Pylint 分 ↑ | 8.55 |
| 圈复杂度 CC ↓ | 17.56 |
| 可维护性 MI ↑ | 48.59 |
| SLOC | 64.19 |
| 每百行问题数 ↓ | 14.19 |
| SonarQube 可维护性问题 ↓ | 1.53 |
| SonarQube 可靠性问题 ↓ | 0.00 |
| SonarQube 安全问题 ↓ | 0.00 |

## 用量与费用

| 指标 | deepseek-flash |
|---|---:|
| 有效调用数 | 121 |
| 输出 token ↓ | 4.34M |
| 延迟中位数 ↓ | 150 s |
| 费用 ↓ | $2.61 |

## 逐题结果

### deepseek-flash

| 题目 | 档 | 子集 | 解出 / 采样 | 平均得分 | 主要失败 |
|---|---|---|---:|---:|---|
| usaco-1443 Roundabout Rounding | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1444 Farmer John's Cheese Block | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1445 It's Mooin' Time | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1446 Cake Game | L2 | USACO 2024-25 | 0/1 | 9.1 | 答案错误 |
| usaco-1447 Deforestation | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1448 2D Conveyor Belt | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1449 Cowdependence | L3 | USACO 2024-25 | 2/3 | 86.7 | 答案错误 |
| usaco-1450 Interstellar Intervals | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1451 Job Completion | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1452 All Pairs Similarity | L4 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1453 It's Mooin' Time | L4 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1454 Maximize Minimum Difference | L4 | USACO 2024-25 | 0/3 | 10.0 | 答案错误 |
| usaco-1467 Astral Superposition | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1468 It's Mooin' Time II | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1469 Cow Checkups | L1 | USACO 2024-25 | 1/1 | 100.0 | 只在官方时限下超时 |
| usaco-1470 Cow Checkups | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1471 Farmer John's Favorite Operation | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1472 Table Recovery | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1473 Median Heap | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1474 Reachable Pairs | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1475 Photo Op | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1476 DFS Order | L4 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1477 Shock Wave | L4 | USACO 2024-25 | 1/3 | 35.7 | 编译错误 |
| usaco-1491 Reflection | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1492 Making Mexes | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1493 Printing Sequences | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1494 The Best Lineup | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1495 Vocabulary Quiz | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1496 Transforming Pairs | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1497 Bessie's Function | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1498 The Best Subsequence | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1499 Friendship Editing | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1502 True or False Test | L4 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1515 Hoof Paper Scissors Minus One | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1516 More Cow Photos | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1517 It's Mooin' Time III | L1 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1519 Compatible Pairs | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1520 Ski Slope | L2 | USACO 2024-25 | 1/1 | 100.0 |  |
| usaco-1521 Moo Decomposition | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1522 Election Queries | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1523 OohMoo Milk | L3 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1525 Lazy Sort | L4 | USACO 2024-25 | 3/3 | 100.0 |  |
| usaco-1526 Package Pickup | L4 | USACO 2024-25 | 1/3 | 56.7 | 运行错误 |
| usaco-1539 Chip Exchange | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1541 Photoshoot | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1542 Lineup Queries | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1543 Mooclear Reactor | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1544 Sliding Window Summation | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1545 COW Traversals | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1546 Milk Buckets | L3 | USACO 2025-26 | 2/3 | 69.0 | 答案错误 |
| usaco-1547 Supervision | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1564 Moo Hunt | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1565 Purchasing Milk | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1567 Declining Invitations | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1568 Farmer John Loves Rotations | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1569 Balancing the Barns | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1570 Lexicographically Smallest Path | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1571 The Chase | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1587 Make All Distinct | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1588 Strange Function | L1 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1590 Clash! | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1591 Milk Buckets | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1592 Point Elimination | L2 | USACO 2025-26 | 1/1 | 100.0 |  |
| usaco-1593 Good Cyclic Shifts | L3 | USACO 2025-26 | 3/3 | 100.0 |  |
| usaco-1595 Random Tree Generation | L3 | USACO 2025-26 | 3/3 | 100.0 |  |

