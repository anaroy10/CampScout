"""Run the currently implemented CampScout ETL phases."""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from etl.clean_activities import ActivityCleaningError
from etl.clean_activities import run_cleaning as run_activity_cleaning
from etl.clean_campgrounds import CampgroundCleaningError
from etl.clean_campgrounds import run_cleaning as run_campground_cleaning


def run_pipeline() -> None:
    """Run activity and campground cleaning in dependency order."""

    run_activity_cleaning()
    run_campground_cleaning()


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
    except CampgroundCleaningError as exc:
        print(f"Pipeline failed during campground cleaning: {exc}", file=sys.stderr)
        return 1

    print("Activity cleaning phase completed.")
    print("Campground cleaning phase completed.")
    print("National-park cleaning: not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
