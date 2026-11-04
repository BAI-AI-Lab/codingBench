"""Figures of the codingBench ladder technical report, from analysis.json and paper_data.json (no problem content).

  python make_figures.py <paper dir>      -> <paper dir>/figures/fig*.pdf

Okabe-Ito colours, one fixed colour per model in every figure; Kimi K3.1 Pro at high effort is the Kimi colour
with hatching; Chinese labels in a CJK sans font next to Arial.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(ROOT, "analysis.json")))
D = json.load(open(os.path.join(ROOT, "paper_data.json")))
OUT = os.path.join(ROOT, "figures")
os.makedirs(OUT, exist_ok=True)
MM = 1 / 25.4
TIERS = ["L1", "L2", "L3", "L4", "L5"]
TN = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式"}
KIMI, HIGH, DS, MM_ = "kimi-k3.1-pro", "kimi-k3.1-pro-high", "deepseek-flash", "MiniMax-M3.1-Flash"
ORDER = [KIMI, HIGH, DS, MM_]
MAIN = [KIMI, DS, MM_]
COLOR = {KIMI: "#009E73", HIGH: "#009E73", DS: "#D55E00", MM_: "#0072B2"}
HATCH = {HIGH: "////"}
NAME = A["names"]
GREY, LIGHT, DARK = "#999999", "#E4E4E4", "#555555"


def style():
    have = {f.name for f in font_manager.fontManager.ttflist}
    latin = [f for f in ("Arial", "Helvetica", "Liberation Sans") if f in have] or ["DejaVu Sans"]
    cjk = [f for f in ("STHeiti", "Heiti SC", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei") if f in have]
    plt.rcParams.update({
        "font.family": latin[:1] + cjk[:1] + ["DejaVu Sans"], "font.size": 7, "axes.labelsize": 7, "axes.titlesize": 7.5,
        "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 6.5, "axes.linewidth": 0.6,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "axes.unicode_minus": False,
        "hatch.linewidth": 0.5, "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300, "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02})


def save(fig, stem):
    fig.savefig(os.path.join(OUT, f"{stem}.pdf"))
    fig.savefig(os.path.join(OUT, f"{stem}.png"))
    plt.close(fig)


def panel(ax, s):
    ax.text(-0.1, 1.08, s, transform=ax.transAxes, fontsize=8.5, fontweight="bold", va="bottom", ha="left")


def main_value(m, t):
    v = A["metrics"][m].get(t)
    if not v:
        return None, None
    return (v["score"], v["score_ci"]) if t == "L5" else (v["pass1"], v["pass1_ci"])


def legend_handles(models):
    return [Patch(facecolor=COLOR[m] if m != HIGH else "white", edgecolor=COLOR[m], hatch=HATCH.get(m), lw=0.6) for m in models], \
           [NAME[m] for m in models]


def fig1():
    """(a) composition by tier and source; (b) the ladder curves with 95% intervals."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 64 * MM), gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axs[0]
    P = D["problems"]
    srcs = [("USACO 2024-25", "#BFBFBF", None), ("USACO 2025-26", "#7F7F7F", None), ("2026", "white", "xxxx"), ("FrontierCS", "white", "....")]
    lab = {"USACO 2024-25": "USACO 2024–25", "USACO 2025-26": "USACO 2025–26", "2026": "EGOI 2026", "FrontierCS": "FrontierCS 算法赛道"}
    for i, t in enumerate(TIERS):
        left = 0
        for s, col, h in srcs:
            n = sum(1 for v in P.values() if v["tier"] == t and v["subset"] == s)
            if n:
                ax.barh(len(TIERS) - 1 - i, n, left=left, color=col, edgecolor="black", lw=0.5, hatch=h, height=0.62)
                left += n
        ax.text(left + 0.8, len(TIERS) - 1 - i, str(left), va="center", fontsize=6.5)
    ax.set_yticks(range(len(TIERS)), [TN[t] for t in TIERS][::-1])
    ax.set_xlabel("题数")
    ax.set_xlim(0, 50)
    ax.tick_params(axis="y", length=0)
    ax.legend([Patch(facecolor=c, edgecolor="black", hatch=h, lw=0.5) for _, c, h in srcs], [lab[s] for s, _, _ in srcs],
              loc="upper right", fontsize=5.8, handlelength=1.4)
    ax.set_title(f"(a) 题库构成（共 {len(P)} 题）")
    ax = axs[1]
    ax.axvspan(3.5, 4.5, color=LIGHT, alpha=0.6, lw=0)
    ax.text(4.0, 101, "连续分", ha="center", fontsize=5.8, color=DARK)
    for m in ORDER:
        xs, ys, lo, hi = [], [], [], []
        for i, t in enumerate(TIERS):
            v, c = main_value(m, t)
            if v is None:
                continue
            xs.append(i), ys.append(v), lo.append(v - c[0]), hi.append(c[1] - v)
        ax.errorbar(xs, ys, yerr=[lo, hi], color=COLOR[m], lw=1.1, ls="--" if m == HIGH else "-", marker="o",
                    ms=3.2, mfc="white" if m == HIGH else COLOR[m], elinewidth=0.5, capsize=1.5, label=NAME[m])
    ax.set_xticks(range(5), [f"{t}\n{A['tier_n'][t]} 题" for t in TIERS])
    ax.set_ylim(0, 105)
    ax.set_xlim(-0.4, 4.4)
    ax.set_ylabel("pass@1（%）/ 平均得分 ↑")
    ax.grid(axis="y", lw=0.3, color=LIGHT)
    ax.legend(loc="lower left", fontsize=5.8)
    ax.set_title("(b) 阶梯曲线（95% 区间；L5 为平均得分）")
    fig.subplots_adjust(wspace=0.32)
    save(fig, "fig1_overview")


def fig2():
    """Construction (once, solid boxes) and evaluation (every model, dashed boxes); outlines only, no fill."""
    fig, ax = plt.subplots(figsize=(170 * MM, 62 * MM))
    ax.set_xlim(-0.5, 100.5)
    ax.set_ylim(0, 46)
    ax.axis("off")
    rows = [("构建（一次，得到固定题单）", "-", 25,
             [("官方来源", "USACO、EGOI 2026、\nFrontierCS：题面、\n测试数据与题解"),
              ("判题校验", "官方解在本机判题程序上\n必须全部通过，否则剔除"),
              ("性能对照", "能通过的官方解中\n最快的一份作为参照"),
              ("固定题单", "L1–L4 全部可用题；\nL5 按题号均匀抽取 30 题")]),
            ("评测（每个模型）", (0, (4, 2.5)), 1,
             [("生成", "L1、L2、L5 每题 1 次，\nL3、L4 每题 3 次"),
              ("判题", "官方时限，按 CPU 时间；\n官方 checker 与计分规则"),
              ("复测与复杂度", "相对官方解的 CPU 时间、\n内存与增长幂次 k"),
              ("报告", "各档正确率与区间、\n配对差值、静态质量、\ntoken 与费用")])]
    for title, ls, y0, steps in rows:
        n = len(steps)
        w = 22.0
        gap = (100 - w * 4) / 3
        x0 = (100 - (n * w + (n - 1) * gap)) / 2
        ax.text(0, y0 + 18.6, title, ha="left", fontsize=6.8, fontweight="bold")
        for i, (head, body) in enumerate(steps):
            x = x0 + i * (w + gap)
            ax.add_patch(Rectangle((x, y0), w, 16, lw=0.7, ls=ls, ec="black", fc="none"))
            ax.text(x + w / 2, y0 + 12, head, ha="center", va="center", fontsize=6.8, fontweight="bold")
            ax.text(x + w / 2, y0 + 5.5, body, ha="center", va="center", fontsize=5.6, color=DARK, linespacing=1.4)
            if i < n - 1:
                ax.annotate("", xy=(x + w + gap - 0.6, y0 + 8), xytext=(x + w + 0.6, y0 + 8),
                            arrowprops={"arrowstyle": "-|>", "lw": 0.6, "color": "black"})
    ax.annotate("", xy=(50, 17.4), xytext=(50, 24.6), arrowprops={"arrowstyle": "-|>", "lw": 0.6, "color": "black"})
    ax.text(51.2, 21, f"固定题单 samples/ladder.json（{len(D['problems'])} 题）", fontsize=5.6, color=DARK, va="center")
    save(fig, "fig2_pipeline")


def grouped(ax, labels, getter, models, fmt="{:.0f}", ymax=105):
    n = len(models)
    width = 0.8 / n
    for r, m in enumerate(models):
        for i, lab in enumerate(labels):
            v, c = getter(m, lab)
            if v is None:
                continue
            x = i + (r - (n - 1) / 2) * width
            ax.bar(x, v, width, color=COLOR[m] if m != HIGH else "white", edgecolor=COLOR[m], hatch=HATCH.get(m), lw=0.6,
                   yerr=[[v - c[0]], [c[1] - v]] if c else None, error_kw={"elinewidth": 0.5, "capsize": 1.2, "capthick": 0.5, "ecolor": DARK})
    ax.set_xticks(range(len(labels)), labels)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, ymax)
    ax.set_xlim(-0.6, len(labels) - 0.4)


def fig3():
    """pass@1 (L1-L4 and pooled) and mean score (L1-L5), 95% intervals."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 60 * MM), gridspec_kw={"width_ratios": [1, 1.1]})
    labs = ["L1", "L2", "L3", "L4", "L1-L4"]

    def p1(m, t):
        v = A["metrics"][m].get(t)
        return (v["pass1"], v["pass1_ci"]) if v and "pass1" in v else (None, None)

    def sc(m, t):
        v = A["metrics"][m].get(t)
        return (v["score"], v["score_ci"]) if v and "score_ci" in v else (None, None)
    grouped(axs[0], labs, p1, ORDER)
    axs[0].set_xticks(range(5), ["L1", "L2", "L3", "L4", "L1–L4\n合计"])
    axs[0].axvline(3.5, color=LIGHT, lw=0.6)
    axs[0].set_ylabel("pass@1（%）↑")
    panel(axs[0], "a")
    grouped(axs[1], TIERS, sc, ORDER)
    axs[1].set_ylabel("平均得分（0–100）↑")
    panel(axs[1], "b")
    h, l = legend_handles(ORDER)
    fig.legend(h, l, loc="upper center", bbox_to_anchor=(0.5, 1.06), ncol=4)
    fig.subplots_adjust(wspace=0.22)
    save(fig, "fig3_scores")


def fig4():
    """Pairwise differences per tier with paired-bootstrap 95% intervals."""
    pairs = [(KIMI, DS), (KIMI, MM_), (DS, MM_)]
    rows = ["L1", "L2", "L3", "L4", "L1-L4", "L5"]
    fig, axs = plt.subplots(1, 3, figsize=(170 * MM, 56 * MM), sharey=True)
    for k, (ax, (a, b)) in enumerate(zip(axs, pairs)):
        p = A["pairs"][f"{a}|{b}"]
        for j, t in enumerate(rows):
            d, (lo, hi) = p[t]["diff"], p[t]["ci"]
            sig = lo > 0 or hi < 0
            col = COLOR[a] if d > 0 else COLOR[b]
            y = len(rows) - 1 - j
            ax.plot([lo, hi], [y, y], color=col if sig else GREY, lw=1.0)
            ax.plot(d, y, "o", ms=3.6 if t == "L1-L4" else 3, mfc=col if sig else "white", mec=col if sig else GREY, mew=0.8)
        ax.axvline(0, color=DARK, lw=0.5)
        ax.axhline(0.5, color=LIGHT, lw=0.5)
        ax.axhline(1.5, color=LIGHT, lw=0.5)
        ax.set_yticks(range(len(rows)), [("L1–L4 合计" if t == "L1-L4" else ("L5（平均得分）" if t == "L5" else t)) for t in rows][::-1])
        ax.set_xlabel("pass@1 差（百分点）/ L5 得分差")
        ax.set_title(f"{NAME[a]}\n− {NAME[b]}", fontsize=6.4)
        ax.set_xlim(-30, 60)
        panel(ax, "abc"[k])
    fig.subplots_adjust(wspace=0.12)
    save(fig, "fig4_pairwise")


def fig5():
    """Kimi K3.1 Pro at high and max: (a) per tier; (b) per sample; (c) output tokens per call."""
    fig, axs = plt.subplots(1, 3, figsize=(170 * MM, 56 * MM), gridspec_kw={"width_ratios": [1, 1.1, 0.9]})
    ax = axs[0]
    for r, m in enumerate([HIGH, KIMI]):
        for i, t in enumerate(["L4", "L5"]):
            v, c = main_value(m, t)
            x = i + (r - 0.5) * 0.36
            ax.bar(x, v, 0.36, color=COLOR[m] if m != HIGH else "white", edgecolor=COLOR[m], hatch=HATCH.get(m), lw=0.6,
                   yerr=[[v - c[0]], [c[1] - v]], error_kw={"elinewidth": 0.5, "capsize": 1.2, "capthick": 0.5, "ecolor": DARK})
            ax.text(x, c[1] + 1.2, f"{v:.1f}", ha="center", va="bottom", fontsize=5)
    ax.set_xticks([0, 1], ["L4 pass@1（%）", "L5 平均得分"])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 112)
    ax.set_ylabel("pass@1（%）/ 平均得分 ↑")
    ax.legend(*legend_handles([HIGH, KIMI]), loc="upper right", fontsize=5.6)
    panel(ax, "a")
    ax = axs[1]
    e = A["effort"]
    for t, mk, col in (("L4", "s", COLOR[KIMI]), ("L5", "o", DARK)):
        xs = [s[1] for s in e[t]["samples"]]
        ys = [s[2] for s in e[t]["samples"]]
        ax.scatter(xs, ys, s=10, marker=mk, facecolors="none" if t == "L5" else col, edgecolors=col, lw=0.6,
                   label=f"{t}（{e[t]['n']} 个采样）")
    ax.plot([0, 100], [0, 100], color=GREY, lw=0.5, ls="--")
    ax.set_xlim(-3, 103)
    ax.set_ylim(-3, 103)
    ax.set_xlabel("high 得分")
    ax.set_ylabel("max 得分")
    ax.legend(loc="lower right", fontsize=5.6)
    ax.set_aspect("equal")
    panel(ax, "b")
    ax = axs[2]
    for r, m in enumerate([HIGH, KIMI]):
        for i, t in enumerate(["L4", "L5"]):
            v = A["effort"][t]["high_out" if m == HIGH else "max_out"] / 1000
            x = i + (r - 0.5) * 0.36
            ax.bar(x, v, 0.36, color=COLOR[m] if m != HIGH else "white", edgecolor=COLOR[m], hatch=HATCH.get(m), lw=0.6)
            ax.text(x, v + 0.8, f"{v:.1f}k", ha="center", va="bottom", fontsize=5)
    ax.set_xticks([0, 1], ["L4（18 个采样）", "L5（30 个采样）"])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("每次调用输出 token（千，含思考）↓")
    panel(ax, "c")
    fig.subplots_adjust(wspace=0.42)
    save(fig, "fig5_effort")


def fig6():
    """(a) output tokens per call, (b) output speed, (c) cost per solved answer, per tier."""
    fig, axs = plt.subplots(1, 3, figsize=(170 * MM, 56 * MM))
    U = A["usage"]

    def bars3(ax, key, scale, fmt, tiers):
        width = 0.26
        for r, m in enumerate(MAIN):
            xs = [i + (r - 1) * width for i in range(len(tiers))]
            v = [(U[m][t].get(key) or 0) * scale for t in tiers]
            ax.bar(xs, v, width, color=COLOR[m], lw=0, label=NAME[m])
            for x, y in zip(xs, v):
                ax.text(x, y * 1.04 if ax.get_yscale() == "log" else y + max(v) * 0.015, fmt.format(y), ha="center", va="bottom", fontsize=4.4, rotation=90)
        ax.set_xticks(range(len(tiers)), tiers)
        ax.tick_params(axis="x", length=0)
    bars3(axs[0], "out_mean", 1 / 1000, "{:.0f}", TIERS)
    axs[0].set_ylabel("每次调用输出 token（千，含思考）↓")
    axs[0].set_ylim(0, 100)
    panel(axs[0], "a")
    bars3(axs[1], "tps_median", 1, "{:.0f}", TIERS)
    axs[1].set_ylabel("输出速度中位数（tokens/s）↑")
    axs[1].set_ylim(0, 250)
    panel(axs[1], "b")
    bars3(axs[2], "cost_per_solved", 100, "{:.1f}", ["L1", "L2", "L3", "L4"])
    axs[2].set_ylabel("每份解出答案的费用（美分）↓")
    axs[2].set_ylim(0, 52)
    panel(axs[2], "c")
    fig.legend(*axs[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 1.06), ncol=3)
    fig.subplots_adjust(wspace=0.38)
    save(fig, "fig6_cost")


style()
for f in (fig1, fig2, fig3, fig4, fig5, fig6):
    f()
print("figures:", sorted(x for x in os.listdir(OUT) if x.endswith(".pdf")))
