"""Write the results tables into README.md between the RESULTS markers, from results/summary.json only."""

from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
ARM_NAMES = {
    "oneshot": "one-shot prompt",
    "rules": "+ rule checks and repair",
    "full": "+ rule checks, LLM fact check and repair",
}


def tables(summary: dict) -> str:
    lines = [
        "| Model | Setup | Clean packs | Rule problems | Unsupported claims (judge flags after review) | Flagged for review "
        "| Shipped with a problem, unflagged | Calls | Cost per pack | Seconds per pack | Cost per clean pack |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["table"]:
        cpc = f"${r['cost_per_clean_pack_usd']:.4f}" if r["cost_per_clean_pack_usd"] is not None else "n/a"
        flagged = "n/a" if r["arm"] == "oneshot" else str(r["flagged_for_review"])
        lines.append(
            f"| {r['model']} | {ARM_NAMES[r['arm']]} | {r['clean_packs']}/{r['packs']} | {r['rule_issues']} "
            f"| {r['unsupported_claims']} (judge flagged {r['judge_flags']}) | {flagged} | {r['shipped_dirty']} "
            f"| {r['calls_per_pack']} | ${r['cost_per_pack_usd']:.4f} | {r['seconds_per_pack']} | {cpc} |"
        )
    lines += ["", "Paired against the one-shot pack from the same draft (95% bootstrap interval over hotel x sample):", ""]
    lines += ["| Model | Setup | Clean-pack rate change | Unsupported claims per pack change |", "|---|---|---|---|"]
    for d in summary["paired"]:
        c, k = d["clean_rate_ci95"], d["claims_per_pack_ci95"]
        lines.append(
            f"| {d['model']} | {ARM_NAMES[d['arm']]} | {d['clean_rate_delta']:+.0%} [{c[0]:+.0%}, {c[1]:+.0%}] "
            f"| {d['claims_per_pack_delta']:+.2f} [{k[0]:+.2f}, {k[1]:+.2f}] |"
        )
    lines += [
        "",
        f"{summary['hotels']} made-up hotels x {summary['samples_per_hotel']} samples per model. Judge (Claude Sonnet 5.5) cost "
        f"${summary['judge_cost_usd']:.2f} in total, not included above; {summary['judge_unparsed']} judge replies unparsed.",
    ]
    return "\n".join(lines)


def update(summary: dict) -> None:
    if not README.exists():
        return
    text = README.read_text()
    if START not in text:
        return
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{START}\n{tables(summary)}\n{END}{tail}")
