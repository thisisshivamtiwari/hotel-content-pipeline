"""results/summary.json -> media/results.png: clean packs and cost per clean pack, by setup and model."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import experiment  # noqa: E402

COLOURS = {"haiku-4.5": "#2a78d6", "sonnet-5.5": "#eb6834"}  # fixed categorical order (blue, orange)
ARMS = {"oneshot": "one-shot", "rules": "+ rule checks", "full": "+ rules + LLM check"}
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def main() -> None:
    s = json.loads((experiment.RESULTS / "summary.json").read_text())
    rows = {(r["model"], r["arm"]): r for r in s["table"]}
    models = list(COLOURS)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=SURFACE)
    panels = [
        ("clean_packs", "Clean packs (of 16)", "{:.0f}"),
        ("cost_per_clean_pack_usd", "Cost per clean pack (USD at API list prices)", "${:.3f}"),
    ]
    for ax, (metric, title, fmt) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        width = 0.38
        for k, m in enumerate(models):
            xs = [i + (k - 0.5) * (width + 0.02) for i in range(len(ARMS))]
            vals = [rows[(m, a)][metric] or 0 for a in ARMS]
            bars = ax.bar(xs, vals, width, color=COLOURS[m], label=m, edgecolor=SURFACE, linewidth=2)
            for b, v in zip(bars, vals, strict=True):
                ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom", fontsize=9, color=INK)
        ax.set_xticks(range(len(ARMS)), list(ARMS.values()), color=MUTED)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.tick_params(colors=MUTED, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#d9d8d4")
        ax.grid(axis="y", color="#ecebe8", linewidth=0.8)
        ax.set_axisbelow(True)
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False, labelcolor=MUTED, loc="upper right", ncol=2)
    note = "Clean = no rule problem and no reviewed unsupported claim. 8 made-up hotels x 2 samples per model."
    fig.suptitle(note, fontsize=9, color=MUTED, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(experiment.ROOT / "media" / "results.png", dpi=150)
