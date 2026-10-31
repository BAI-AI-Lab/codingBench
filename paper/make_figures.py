"""Figures of the ladder technical report, from analysis.json (no problem content).

  python make_figures.py <paper dir>      -> <paper dir>/figures/fig*.pdf

Okabe-Ito colours, one fixed colour per model in every figure (as in the mmBench report); diagrams and composition
plots are outlines only (solid / dashed, hatching), no colour fill.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(ROOT, "analysis.json")))
OUT = os.path.join(ROOT, "figures")
os.makedirs(OUT, exist_ok=True)
MM = 1 / 25.4
TIERS = A["tiers"]
CLOSED = TIERS[:4]
TIER_NAME = {"L1": "L1 基础", "L2": "L2 中等", "L3": "L3 困难", "L4": "L4 顶尖", "L5": "L5 开放式"}
ORDER = A["models"]
COLOR = {"deepseek-flash": "#D55E00", "MiniMax-M3.1-Flash": "#0072B2"}
NAME = A["names"]
SHORT = {"deepseek-flash": "DeepSeek", "MiniMax-M3.1-Flash": "MiniMax"}
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
    ax.text(-0.08, 1.1, s, transform=ax.transAxes, fontsize=8.5, fontweight="bold", va="bottom", ha="left")


def headline(m, t):
    """pass@1 for L1-L4, mean score for L5 (the tier's main number) and its interval"""
    k = "score" if t == "L5" else "pass1"
    return A["point"][m][t][k], A["ci"][m][t][k]


def fig1():
    """(a) composition of the ladder; (b) the two models' main number per tier."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 60 * MM), gridspec_kw={"width_ratios": [1, 1.15]})
    ax = axs[0]
    hatch_of = {"USACO 2024-25": "", "USACO 2025-26": "////", "2026": "xxxx", "FrontierCS": "...."}
    parts = {t: [(name, n, hatch_of[name]) for name, n in sorted(A["composition"][t].items(), key=lambda x: list(hatch_of).index(x[0]))]
             for t in TIERS}
    label = {"USACO 2024-25": "USACO 2024–25", "USACO 2025-26": "USACO 2025–26", "2026": "EGOI 2026",
             "FrontierCS": "FrontierCS 算法赛道"}
    seen = set()
    for j, t in enumerate(TIERS):
        y = len(TIERS) - 1 - j
        x = 0
        for name, n, hatch in parts[t]:
            ax.barh(y, n, left=x, height=0.62, fc="white", ec="black", lw=0.6, hatch=hatch,
                    label=label[name] if name not in seen else None)
            seen.add(name)
            x += n
        ax.text(x + 0.6, y, str(x), va="center", fontsize=6)
    ax.set_yticks(range(len(TIERS)), [TIER_NAME[t] for t in TIERS][::-1])
    ax.set_xlabel("题数")
    ax.set_xlim(0, 44)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper right", fontsize=5.8, handlelength=1.8, bbox_to_anchor=(1.04, 1.02))
    ax.set_title(f"(a) 题库构成（共 {A['n_problems']} 题）")
    ax = axs[1]
    xs = range(len(TIERS))
    for r, m in enumerate(ORDER):
        v, c = zip(*(headline(m, t) for t in TIERS))
        off = [x + (r - 0.5) * 0.12 for x in xs]
        ax.errorbar(off, v, yerr=[[a - lo for a, (lo, _) in zip(v, c)], [hi - a for a, (_, hi) in zip(v, c)]],
                    fmt="-o", ms=3.4, lw=1.1, color=COLOR[m], elinewidth=0.6, capsize=1.6, label=NAME[m])
    ax.axvline(3.5, color=GREY, lw=0.6, ls="--")
    ax.text(3.55, 103, "右侧为连续分", fontsize=5.6, color=DARK, va="top")
    ax.set_xticks(list(xs), [f"{t}\n{A['tier_n'][t]} 题" for t in TIERS])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 105)
    ax.set_ylabel("pass@1（%）/ 平均得分 ↑")
    ax.grid(axis="y", lw=0.3, color=LIGHT)
    ax.legend(loc="lower left")
    ax.set_title("(b) 两个模型的阶梯曲线（95% 区间）")
    fig.subplots_adjust(wspace=0.42)
    save(fig, "fig1_overview")


def fig2():
    """Build once (solid boxes), then evaluate every model (dashed boxes); outlines only."""
    fig, ax = plt.subplots(figsize=(170 * MM, 62 * MM))
    ax.set_xlim(-0.5, 100.5)
    ax.set_ylim(0, 46)
    ax.axis("off")
    rows = [("构建（一次，得到固定题单）", "-", 25,
             [("官方来源", "USACO、EGOI 2026、\nFrontierCS：题面、测试与题解"),
              ("判题校验", "官方解在本机判题器上\n必须全部通过，否则剔除"),
              ("性能对照", "能通过的官方解中\n最快的一份作为参照"),
              ("固定题单", "L1–L4 全部可用题；\nL5 按题号均匀抽 30 题")]),
            ("评测（每个模型）", (0, (4, 2.5)), 1,
             [("生成", "L1/L2/L5 每题 1 次、\nL3/L4 每题 3 次"),
              ("判题", "宽时限（官方 5 倍）运行一次，\n同时得出官方时限判定"),
              ("复测与复杂度", "相对官方解的 CPU 时间、\n内存与增长幂次 k"),
              ("报告", "各档正确率、配对差值、\n静态质量、token 与费用")])]
    w = 22.0
    gap = (100 - w * 4) / 3
    for title, ls, y0, steps in rows:
        ax.text(0, y0 + 18.6, title, ha="left", fontsize=6.8, fontweight="bold")
        for i, (head, body) in enumerate(steps):
            x = i * (w + gap)
            ax.add_patch(Rectangle((x, y0), w, 16, lw=0.7, ls=ls, ec="black", fc="none"))
            ax.text(x + w / 2, y0 + 12, head, ha="center", va="center", fontsize=6.8, fontweight="bold")
            ax.text(x + w / 2, y0 + 5.5, body, ha="center", va="center", fontsize=5.6, color=DARK, linespacing=1.4)
            if i < len(steps) - 1:
                ax.annotate("", xy=(x + w + gap - 0.6, y0 + 8), xytext=(x + w + 0.6, y0 + 8),
                            arrowprops={"arrowstyle": "-|>", "lw": 0.6, "color": "black"})
    ax.annotate("", xy=(50, 17.4), xytext=(50, 24.6), arrowprops={"arrowstyle": "-|>", "lw": 0.6, "color": "black"})
    ax.text(51.2, 21, f"固定题单 samples/ladder.json（{A['n_problems']} 题）", fontsize=5.6, color=DARK, va="center")
    save(fig, "fig2_pipeline")


def grouped(ax, vals, labels, fmt="{:.0f}", width=0.34, cis=None):
    for r, m in enumerate(ORDER):
        xs = [i + (r - 0.5) * width for i in range(len(labels))]
        v = vals[m]
        kw = {}
        if cis:
            kw = {"yerr": [[a - c[0] for a, c in zip(v, cis[m])], [c[1] - a for a, c in zip(v, cis[m])]],
                  "error_kw": {"elinewidth": 0.5, "capsize": 1.2, "capthick": 0.5, "ecolor": DARK}}
        b = ax.bar(xs, v, width, color=COLOR[m], lw=0, label=NAME[m], **kw)
        ax.bar_label(b, labels=[fmt.format(x) for x in v], padding=1, fontsize=5)
    ax.set_xticks(range(len(labels)), labels)
    ax.tick_params(axis="x", length=0)


def fig3():
    """(a) pass@1 with the lenient and the official time limit; (b) mean score incl. L5."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 56 * MM), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axs[0]
    labels = [f"{t}" for t in CLOSED] + ["L1–L4"]
    groups = CLOSED + ["L1-L4"]
    grouped(ax, {m: [A["point"][m][g]["pass1"] for g in groups] for m in ORDER}, labels,
            cis={m: [A["ci"][m][g]["pass1"] for g in groups] for m in ORDER})
    for r, m in enumerate(ORDER):
        xs = [i + (r - 0.5) * 0.34 for i in range(len(CLOSED))]
        ax.plot(xs, [A["tier"][m][t]["pass1_strict"] for t in CLOSED], ls="none", marker="_", ms=7, mew=1.0, color="black",
                label="官方时限" if r == 0 else None)
    ax.set_ylim(0, 112)
    ax.set_ylabel("pass@1（%）↑")
    ax.set_title("(a) pass@1：柱为宽时限，横线为官方时限")
    h, l_ = ax.get_legend_handles_labels()
    fig.legend(h[1:] + h[:1], l_[1:] + l_[:1], loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=3, fontsize=6.5)
    ax = axs[1]
    grouped(ax, {m: [A["point"][m][t]["score"] for t in TIERS] for m in ORDER}, TIERS,
            cis={m: [A["ci"][m][t]["score"] for t in TIERS] for m in ORDER})
    ax.set_ylim(0, 112)
    ax.set_ylabel("平均得分（0–100，宽时限）↑")
    ax.set_title("(b) 平均得分（含部分分）")
    fig.subplots_adjust(wspace=0.25)
    save(fig, "fig3_scores")


def fig4():
    """MiniMax - DeepSeek per tier with paired-bootstrap intervals, and per-problem wins / ties / losses."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 52 * MM), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axs[0]
    rows = [(t, "pass1") for t in CLOSED] + [("L1-L4", "pass1"), ("L5", "score")]
    ds, mm = ORDER
    for j, (g, k) in enumerate(rows):
        d, (lo, hi) = A["diff"][g][k]["diff"], A["diff"][g][k]["ci"]
        sig = lo > 0 or hi < 0
        col = COLOR[mm] if d > 0 else COLOR[ds]
        y = len(rows) - 1 - j
        ax.plot([lo, hi], [y, y], color=col if sig else GREY, lw=1.0)
        ax.plot(d, y, "o", ms=3.6, mfc=col if sig else "white", mec=col if sig else GREY, mew=0.8)
        ax.text(26, y, f"{d:+.1f}", va="center", ha="right", fontsize=5.8)
    ax.axvline(0, color=DARK, lw=0.5)
    ax.axhline(0.5, color=LIGHT, lw=0.5)
    ax.axhline(1.5, color=LIGHT, lw=0.5)
    ax.set_yticks(range(len(rows)), [("L1–L4 合计" if g == "L1-L4" else g) + ("（平均得分）" if k == "score" else "（pass@1）")
                                      for g, k in rows][::-1])
    ax.set_xlim(-40, 27)
    ax.set_xlabel("MiniMax − DeepSeek（百分点 / 分，95% 区间）")
    ax.set_title("(a) 逐档差值；实心为区间不含 0")
    ax = axs[1]
    groups = TIERS
    y = list(range(len(groups)))[::-1]
    for yy, g in zip(y, groups):
        w = A["wtl"][g]
        n = w["deepseek_better"] + w["tie"] + w["minimax_better"]
        x = 0
        for key, fc, ec, hatch in (("deepseek_better", COLOR[ds], COLOR[ds], ""), ("tie", "white", "black", ""),
                                   ("minimax_better", COLOR[mm], COLOR[mm], "")):
            share = 100 * w[key] / n
            ax.barh(yy, share, left=x, height=0.62, fc=fc, ec=ec, lw=0.6, hatch=hatch)
            if w[key]:
                ax.text(x + share / 2, yy, str(w[key]), ha="center", va="center", fontsize=5.6,
                        color="white" if key != "tie" else "black")
            x += share
        p = w["p"]
        ax.text(101.5, yy, f"p = {p:.3f}" if p >= 0.001 else "p < 0.001", va="center", fontsize=5.6)
    ax.set_yticks(y, [f"{g}（n = {A['tier_n'][g]}）" for g in groups])
    ax.set_xlim(0, 100)
    ax.set_xlabel("占该档题数的比例（%）")
    ax.tick_params(axis="y", length=0)
    from matplotlib.patches import Patch
    ax.legend([Patch(fc=COLOR[ds]), Patch(fc="white", ec="black", lw=0.6), Patch(fc=COLOR[mm])],
              ["DeepSeek 更好", "持平", "MiniMax 更好"], loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=6)
    ax.set_title("(b) 逐题胜负（按平均得分）")
    fig.subplots_adjust(wspace=0.6)
    save(fig, "fig4_pairwise")


def fig5():
    """(a) CPU time relative to the official solution; (b) time-complexity classes."""
    fig, axs = plt.subplots(1, 2, figsize=(170 * MM, 54 * MM), gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axs[0]
    grouped(ax, {m: [A["tier"][m][t]["perf_geo"] for t in CLOSED] for m in ORDER}, CLOSED, fmt="{:.2f}×")
    ax.axhline(1, color="black", lw=0.6, ls="--")
    ax.text(-0.55, 1.02, "与官方解相同", fontsize=5.6, ha="left", va="bottom", color=DARK)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel("CPU 时间 ÷ 官方解（几何平均）↓")
    ax.set_title("(a) 解出答案的运行时间")
    ax = axs[1]
    classes = [("better", "更优", "xxxx"), ("same", "同阶", ""), ("worse", "更差", "...."), ("uncertain", "不确定", "////")]
    width = 0.36
    for r, m in enumerate(ORDER):
        for i, t in enumerate(CLOSED):
            c = A["complexity"][m][t]["time"]["classes"]
            tot = sum(c.get(k, 0) for k, *_ in classes)
            x0 = 0
            xx = i + (r - 0.5) * width
            for k, lab, hatch in classes:
                v = 100 * c.get(k, 0) / tot if tot else 0
                ax.bar(xx, v, width * 0.92, bottom=x0, fc="white", ec=COLOR[m], lw=0.6, hatch=hatch)
                x0 += v
            ax.text(xx, 101, SHORT[m][0], ha="center", va="bottom", fontsize=5.4, color=COLOR[m])
    ax.set_xticks(range(len(CLOSED)), CLOSED)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 110)
    ax.set_ylabel("可判定答案中的比例（%）")
    from matplotlib.patches import Patch
    ax.legend([Patch(fc="white", ec="black", lw=0.6, hatch=h) for _, _, h in classes], [lab for _, lab, _ in classes],
              loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4, fontsize=6)
    ax.set_title("(b) 时间复杂度相对官方解（D = DeepSeek，M = MiniMax）")
    fig.subplots_adjust(wspace=0.32)
    save(fig, "fig5_efficiency")


def fig6():
    """(a) output tokens per call; (b) median latency; (c) cost per solved sample, by tier."""
    fig, axs = plt.subplots(1, 3, figsize=(170 * MM, 52 * MM))
    U = {m: A["usage"][m]["per_tier"] for m in ORDER}
    grouped(axs[0], {m: [U[m][t]["completion"] / U[m][t]["calls"] / 1000 for t in TIERS] for m in ORDER}, TIERS,
            fmt="{:.0f}")
    axs[0].set_ylabel("每次调用输出 token（千，含思考）↓")
    axs[0].set_title("(a) 输出长度")
    grouped(axs[1], {m: [U[m][t]["latency_median"] / 60 for t in TIERS] for m in ORDER}, TIERS, fmt="{:.1f}")
    axs[1].set_ylabel("每次调用延迟中位数（分钟）↓")
    axs[1].set_title("(b) 延迟")
    solved = {m: {t: A["tier"][m][t]["pass1"] * A["tier"][m][t]["samples"] / 100 for t in CLOSED} for m in ORDER}
    grouped(axs[2], {m: [100 * U[m][t]["cost"] / solved[m][t] for t in CLOSED] for m in ORDER}, CLOSED, fmt="{:.1f}")
    axs[2].set_ylabel("每份解出答案的费用（美分）↓")
    axs[2].set_title("(c) 每份解出答案的费用")
    fig.legend(*axs[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 1.1), ncol=2, fontsize=6.5)
    fig.subplots_adjust(wspace=0.42)
    save(fig, "fig6_cost")


style()
for f in (fig1, fig2, fig3, fig4, fig5, fig6):
    f()
print("figures:", sorted(os.listdir(OUT)))
