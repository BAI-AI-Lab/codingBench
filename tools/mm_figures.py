"""The capability-profile chart of a multimodal ladder report, in the Nature style of ladder_figures.py: one group of
bars per capability plus the overall score, one bar per model, 95% intervals as error bars, a value on every bar.

  draw(profile, out_dir) -> ["fig_profile"]   (profile = mm_report.profile(stats); writes .pdf and .png)

Importing this module raises ImportError when matplotlib is missing.
"""
import ladder_figures as F  # noqa: F401  (raises ImportError without matplotlib)
import mm_lib as M

plt = F.plt
COLORS = ("#0072B2", "#D55E00", "#009E73", "#E69F00", "#56B4E9", "#CC79A7", "#F0E442")  # Okabe-Ito


def draw(p, out_dir):
    F.style()
    n = len(p["names"])
    labels = [M.CAP_NAME[c] for c in p["caps"]] + ["总分"]
    width = min(0.8 / n, 0.38)
    fig, ax = plt.subplots(figsize=(183 * F.MM, 62 * F.MM))
    for r in range(n):
        vals = [p["cap"][r][c] for c in p["caps"]] + [p["overall"][r]]
        cis = [p["cap_ci"][r][c] for c in p["caps"]] + [p["overall_ci"][r]]
        xs = [i + (r - (n - 1) / 2) * width for i in range(len(labels))]
        err = [[v - c[0] for v, c in zip(vals, cis)], [c[1] - v for v, c in zip(vals, cis)]]
        bars = ax.bar(xs, vals, width, color=COLORS[r % len(COLORS)], linewidth=0, label=p["names"][r],
                      yerr=err, error_kw={"elinewidth": 0.5, "capsize": 1.2, "capthick": 0.5, "ecolor": F.DARK})
        ax.bar_label(bars, labels=[f"{v:.0f}" for v in vals], padding=1, fontsize=5, label_type="center", color="white")
    ax.axvline(len(labels) - 1.5, color=F.LIGHT, linewidth=0.5)
    ax.set_xticks(range(len(labels)), labels)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("得分 (0-100) ↑")
    ax.set_ylim(0, 105)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=min(n, 4))
    return [F.save(fig, out_dir, "fig_profile")]
