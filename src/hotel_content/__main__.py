"""python -m hotel_content run|report|ci|render

run     record any missing model calls (HCP_MODE=record) and write results/
report  rebuild results/summary.json and the README tables from results/packs.jsonl and the audit
ci      replay every call from cassettes, check results reproduce exactly, and apply the gate (evals/gate.yaml)
render  draw the image post and an animatic of the reel for each hotel (renders/)
demo    terminal walk-through of one hotel and the results table (for the demo video)
"""

import argparse
import json
import sys

from . import experiment, readme


def main() -> int:
    ap = argparse.ArgumentParser(prog="hotel_content")
    ap.add_argument("cmd", choices=["run", "report", "ci", "render", "demo"])
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--hotels", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pause", type=float, default=0.0)
    a = ap.parse_args()
    if a.cmd == "run":
        rows = experiment.run_all(tuple(a.models) if a.models else tuple(experiment.llm.MODELS), a.hotels, a.workers)
        summary = experiment.write(rows)
        readme.update(summary)
        print(json.dumps(summary["table"], indent=1))
        return 0
    if a.cmd == "report":
        rows = [json.loads(line) for line in (experiment.RESULTS / "packs.jsonl").read_text().splitlines()]
        readme.update(experiment.write(rows))
        from . import chart

        chart.main()
        return 0
    if a.cmd == "ci":
        from . import gate

        return gate.main()
    if a.cmd == "demo":
        from . import demo

        demo.main(a.pause)
        return 0
    from . import render

    render.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
