"""Bar charts for the head-to-head section of a two-model ladder report, in Nature figure style: 183 mm (double
column) or 89 mm (single column) wide, Arial 5-7 pt, lowercase bold panel letters, no top/right spines, outward
ticks, frameless legends, a value on every bar, colour-blind-safe colours (Okabe-Ito), fonts embedded as TrueType.

  draw(comparison, out_dir) -> the stems written (fig_scores, fig_h2h, fig_cost, fig_diff; each .pdf and .png)

`comparison` is ladder_report.comparison(stats). Chinese labels fall back to a CJK sans font (Heiti on the Mac,
Noto Sans CJK on Linux) next to Arial. Importing this module raises ImportError when matplotlib is missing.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

MM = 1 / 25.4
COLORS = ("#0072B2", "#D55E00")  # model A, model B (Okabe-Ito blue, vermillion)
GREY, LIGHT, DARK = "#BBBBBB", "#E4E4E4", "#7A7A7A"
CJK = ("STHeiti", "Heiti SC", "Heiti TC", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
       "Arial Unicode MS")


def style():
    have = {f.name for f in font_manager.fontManager.ttflist}
    latin = [f for f in ("Arial", "Helvetica", "Liberation Sans") if f in have] or ["DejaVu Sans"]
    plt.rcParams.update({
        "font.family": latin[:1] + [f for f in CJK if f in have][:1] + ["DejaVu Sans"],
        "font.size": 7, "axes.labelsize": 7, "axes.titlesize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6,
        "legend.fontsize": 6, "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5, "xtick.direction": "out", "ytick.direction": "out",
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "legend.handlelength": 1.0,
        "legend.handleheight": 0.7, "legend.columnspacing": 1.0, "axes.unicode_minus": False, "pdf.fonttype": 42,
        "ps.fonttype": 42, "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def letter(ax, s):
    ax.text(-0.1, 1.06, s, transform=ax.transAxes, fontsize=8, fontweight="bold", va="bottom", ha="left")


def save(fig, out_dir, stem):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out_dir, f"{stem}.{ext}"))
    plt.close(fig)
    return stem


def wrap(label):
    """A tier label on two lines under a bar group ("L1 基础" -> "L1\n基础")."""
    return label.replace(" ", "\n", 1)


def pairs(ax, labels, values, fmt, colors=COLORS, width=0.38, ylabel="", ymax=None, legend=None):
    """Grouped vertical bars, one group per label and one bar per series, the value on top of each bar."""
    n = len(values)
    xs = range(len(labels))
    top = max((v for vs in values for v in vs if v is not None), default=1) or 1
    for i, (vs, c) in enumerate(zip(values, colors)):
        off = (i - (n - 1) / 2) * width
        pos = [x + off for x, v in zip(xs, vs) if v is not None]
        val = [v for v in vs if v is not None]
        bars = ax.bar(pos, val, width, color=c, linewidth=0, label=legend[i] if legend else None)
        ax.bar_label(bars, labels=[fmt(v) for v in val], padding=1, fontsize=5)
    ax.set_xticks(list(xs), [wrap(x) for x in labels])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, ymax if ymax else top * 1.18)
    ax.set_xlim(-0.6, len(labels) - 0.4)


def scores(c, out_dir):
    a, b = c["short"]
    fig, axs = plt.subplots(2, 2, figsize=(183 * MM, 108 * MM))
    disc = [r for r in c["scores"] if not r["continuous"]]
    pct = lambda v: f"{v:.1f}"  # noqa: E731
    pairs(axs[0, 0], [r["label"] for r in disc], list(zip(*[r["pass1"] for r in disc])), pct, ylabel="pass@1, 宽时限 (%) ↑", ymax=112)
    pairs(axs[0, 1], [r["label"] for r in disc], list(zip(*[r["pass1_strict"] for r in disc])), pct, ylabel="pass@1, 官方时限 (%) ↑", ymax=112)
    allr = c["scores"]
    pairs(axs[1, 0], [r["label"] for r in allr], list(zip(*[r["score"] for r in allr])), pct, ylabel="平均得分, 宽时限 (0–100) ↑", ymax=112)
    ax = axs[1, 1]
    d1 = [None if r["continuous"] else r["pass1"][1] - r["pass1"][0] for r in allr]
    d2 = [r["score"][1] - r["score"][0] for r in allr]
    pairs(ax, [r["label"] for r in allr], [d1, d2], lambda v: f"{v:+.1f}", colors=(DARK, GREY),
          ylabel=f"差值 ({b} − {a})", legend=["pass@1, 宽时限", "平均得分, 宽时限"])
    lo = min(v for v in d1 + d2 if v is not None)
    hi = max(v for v in d1 + d2 if v is not None)
    span = max(hi, 0) - min(lo, 0) or 1
    ax.set_ylim(min(lo, 0) - 0.18 * span, max(hi, 0) + 0.18 * span)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.spines["bottom"].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
    for ax_, s in zip(axs.flat, "abcd"):
        letter(ax_, s)
    fig.legend(handles=[Patch(color=COLORS[0], label=c["names"][0]), Patch(color=COLORS[1], label=c["names"][1])],
               loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(h_pad=2.2, w_pad=2.0)
    return save(fig, out_dir, "fig_scores")


def stacked(ax, labels, parts, colors, names, right=None):
    """Horizontal stacked bars as shares of the problems in a row (each bar 100%), top row first; the count inside
    each segment, the number of problems in the row label, an optional note right of each bar."""
    ys = list(range(len(labels)))[::-1]
    totals = [sum(p) for p in parts]
    left = [0.0] * len(labels)
    for vals, col, name in zip(zip(*parts), colors, names):
        share = [100 * v / t if t else 0 for v, t in zip(vals, totals)]
        bars = ax.barh(ys, share, left=left, color=col, height=0.62, linewidth=0, label=name)
        ax.bar_label(bars, labels=[str(v) if v else "" for v in vals], label_type="center", fontsize=5,
                     color="white" if col in COLORS or col == DARK else "black")
        left = [x + v for x, v in zip(left, share)]
    if right:
        for y, t in zip(ys, right):
            ax.text(102, y, t, va="center", ha="left", fontsize=5, clip_on=False)
    ax.set_yticks(ys, [f"{lab} (n = {t})" for lab, t in zip(labels, totals)])
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("题目占比 (%)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(names), borderaxespad=0.2)


def h2h(c, out_dir):
    a, b = c["short"]
    fig, axs = plt.subplots(1, 2, figsize=(183 * MM, 58 * MM))
    rows = c["h2h"]
    fp = lambda p: "" if p is None else "p < 0.001" if p < 0.001 else f"p = {p:.3f}"  # noqa: E731
    stacked(axs[0], [r["label"] for r in rows], [(r["wins"][0], r["tie"], r["wins"][1]) for r in rows], (COLORS[0], GREY, COLORS[1]),
            [f"{a} 更好", "持平", f"{b} 更好"], right=[fp(r["p"]) for r in rows])
    sol = [r for r in rows if r["solve"] is not None]
    lab = [r["label"] if r is not rows[-1] else f"{c['discrete'][0]}–{c['discrete'][-1]} 合计" for r in sol]
    stacked(axs[1], lab, [tuple(r["solve"]) for r in sol], (DARK, COLORS[0], COLORS[1], LIGHT),
            ["都解出", f"只有 {a}", f"只有 {b}", "都没解出"])
    letter(axs[0], "a")
    letter(axs[1], "b")
    fig.tight_layout(w_pad=6.0)
    return save(fig, out_dir, "fig_h2h")


def cost(c, out_dir):
    fig, axs = plt.subplots(2, 2, figsize=(183 * MM, 108 * MM))
    rows = c["cost"]
    tiers = [r for r in rows if not r["total"]]
    total = next((r for r in rows if r["total"]), None)
    pairs(axs[0, 0], [r["label"] for r in rows], list(zip(*[[None if v is None else v / 1000 for v in r["tok"]] for r in rows])),
          lambda v: f"{v:.1f}", ylabel="每次输出 token (千) ↓")
    pairs(axs[0, 1], [r["label"] for r in rows], list(zip(*[r["lat"] for r in rows])), lambda v: f"{v:.0f}", ylabel="延迟中位数 (秒) ↓")
    pairs(axs[1, 0], [r["label"] for r in tiers], list(zip(*[r["cost"] for r in tiers])), lambda v: f"{v:.2f}", ylabel="费用 (美元) ↓")
    if total and None not in total["cost"]:
        axs[1, 0].text(0.02, 0.97, f"合计: {c['short'][0]} \\${total['cost'][0]:.2f}, {c['short'][1]} \\${total['cost'][1]:.2f}",
                       transform=axs[1, 0].transAxes, va="top", fontsize=6)
    ps = [r for r in rows if not r["per_solved_na"]]
    lab = [r["label"] if not r["total"] else f"{c['discrete'][0]}–{c['discrete'][-1]} 合计" for r in ps]
    pairs(axs[1, 1], lab, list(zip(*[r["per_solved"] for r in ps])), lambda v: f"{v:.3f}", ylabel="每份解出答案的费用 (美元) ↓")
    for ax_, s in zip(axs.flat, "abcd"):
        letter(ax_, s)
    fig.legend(handles=[Patch(color=COLORS[0], label=c["names"][0]), Patch(color=COLORS[1], label=c["names"][1])],
               loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(h_pad=2.2, w_pad=2.0)
    return save(fig, out_dir, "fig_cost")


def diff(c, out_dir):
    rows = c["diff"]
    if not rows:
        return None
    a, b = c["short"]
    fig, ax = plt.subplots(figsize=(120 * MM, (14 + 4.2 * len(rows)) * MM))
    ys = list(range(len(rows)))[::-1]
    ds = [r["d"] for r in rows]
    bars = ax.barh(ys, ds, color=[COLORS[1] if d > 0 else COLORS[0] for d in ds], height=0.62, linewidth=0)
    ax.bar_label(bars, labels=[f"{d:+.1f}" for d in ds], padding=1.5, fontsize=5)
    ax.set_yticks(ys, [f"{r['pid']} ({r['tier']})" for r in rows])
    ax.tick_params(axis="y", length=0)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.spines["left"].set_visible(False)
    m = max(abs(d) for d in ds)
    ax.set_xlim(-m * 1.2 if min(ds) < 0 else -m * 0.05, m * 1.2 if max(ds) > 0 else m * 0.05)
    ax.set_xlabel(f"平均得分差 ({b} − {a})")
    ax.legend(handles=[Patch(color=COLORS[0], label=f"{a} 更好"), Patch(color=COLORS[1], label=f"{b} 更好")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
    fig.tight_layout()
    return save(fig, out_dir, "fig_diff")


def draw(c, out_dir):
    style()
    out = []
    for f in (scores, h2h, cost, diff):
        stem = f(c, out_dir)
        if stem:
            out.append(stem)
    return out


if __name__ == "__main__":  # quick look: python ladder_figures.py <report.json> <out dir>
    import json
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ladder_report
    print(draw(ladder_report.comparison(json.load(open(sys.argv[1]))), sys.argv[2]))
