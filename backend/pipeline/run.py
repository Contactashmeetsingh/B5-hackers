"""Run the whole pipeline, stage 1 to 6, in order.

  python -m backend.pipeline.run                    # cache first: no network if caches exist
  python -m backend.pipeline.run --refresh          # every stage re-fetches / recomputes
  python -m backend.pipeline.run --from-stage 4     # rescore only (after lane B updates genomic_context)

Stage modules are imported inside each stage function, so a module that is
missing or half-written breaks only its own stage, not importing this file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend import config


def _literature(refresh: bool):
    from backend.pipeline import literature
    return literature.run(refresh=refresh), config.PAPERS_PATH


def _targets(refresh: bool):
    from backend.pipeline import targets
    return targets.run(refresh=refresh), config.GENE_CANDIDATES_PATH


def _genomic(refresh: bool):
    from backend.pipeline import genomic
    return genomic.run(refresh=refresh), config.GENOMIC_CONTEXT_PATH


def _gene_scores(refresh: bool):
    from backend.pipeline import scoring
    return scoring.run_gene_scores(refresh=refresh), config.GENE_SCORES_PATH


def _trials(refresh: bool):
    from backend.pipeline import trials
    return trials.run(refresh=refresh), config.TRIALS_PATH


def _rankings(refresh: bool):
    from backend.pipeline import scoring
    return scoring.run_trial_rankings(refresh=refresh), config.RANKINGS_PATH


# Order matters: 4 needs 1-3, and 6 needs 4 and 5 (AGENTS.md section 4).
STAGES = [
    (1, "literature", _literature),
    (2, "gene targets", _targets),
    (3, "genomic context", _genomic),
    (4, "gene scores", _gene_scores),
    (5, "trials", _trials),
    (6, "trial rankings", _rankings),
]


def _mock_count(rows) -> str:
    """How many rows are mock, or rest on mock inputs (rankings). "-" if rows carry no source."""
    if rows and hasattr(rows[0], "is_mock"):
        return str(sum(r.is_mock for r in rows))
    if rows and hasattr(rows[0], "mock_inputs"):
        return str(sum(bool(r.mock_inputs) for r in rows))
    return "-"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build every cache and data/output/rankings.json")
    ap.add_argument("--refresh", action="store_true", help="ignore caches and call the network")
    ap.add_argument("--from-stage", type=int, default=1, choices=[n for n, _, _ in STAGES],
                    help="skip earlier stages and use their cached output")
    args = ap.parse_args(argv)

    for n, name, fn in STAGES:
        if n < args.from_stage:
            continue
        try:
            rows, path = fn(args.refresh)
        except ImportError as exc:
            sys.exit(f"[{n}] {name}: stage module not available yet ({exc}). "
                     f"Use --from-stage {n + 1} to run on the cached output.")
        print(f"[{n}] {name:<16} {len(rows):>4} rows  mock: {_mock_count(rows):>4}  -> {_rel(path)}")


if __name__ == "__main__":
    main()
