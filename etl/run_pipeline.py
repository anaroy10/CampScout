"""Run the currently implemented CampScout ETL phases."""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from etl.clean_activities import ActivityCleaningError, run_cleaning


def run_pipeline() -> None:
    """Run activity cleaning; later source phases are intentionally pending."""

    run_cleaning()


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("run_pipeline does not accept arguments", file=sys.stderr)
        return 2
    try:
        run_pipeline()
    except ActivityCleaningError as exc:
        print(f"Pipeline failed during activity cleaning: {exc}", file=sys.stderr)
        return 1

    print("Activity cleaning phase completed.")
    print("Campground cleaning: not implemented.")
    print("National-park cleaning: not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
