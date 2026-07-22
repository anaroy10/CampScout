"""Run the complete CampScout CSV ETL pipeline in dependency order."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

from etl.calculate_distances import run_calculation as run_distance_calculation
from etl.clean_activities import ActivityCleaningError
from etl.clean_activities import run_cleaning as run_activity_cleaning
from etl.clean_campgrounds import CampgroundCleaningError
from etl.clean_campgrounds import run_cleaning as run_campground_cleaning
from etl.clean_parks import ParkCleaningError
from etl.clean_parks import run_cleaning as run_park_cleaning


PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports/generated")


class PipelineError(RuntimeError):
    """A phase-aware failure from the complete ETL pipeline."""


def run_pipeline() -> None:
    """Create output directories and run all ETL phases in dependency order."""

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    phases = (
        ("activity cleaning", run_activity_cleaning),
        ("campground cleaning", run_campground_cleaning),
        ("national-park cleaning", run_park_cleaning),
        ("distance calculation", run_distance_calculation),
    )
    for phase_name, phase in phases:
        print(f"Starting {phase_name} phase.")
        try:
            phase()
        except (ActivityCleaningError, CampgroundCleaningError, ParkCleaningError) as exc:
            raise PipelineError(f"Pipeline failed during {phase_name}: {exc}") from exc
        except Exception as exc:
            # The CLI boundary reports an actionable phase and returns non-zero;
            # KeyboardInterrupt and SystemExit deliberately remain uncaught.
            raise PipelineError(f"Pipeline failed during {phase_name}: {exc}") from exc
        print(f"Completed {phase_name} phase.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("run_pipeline does not accept arguments", file=sys.stderr)
        return 2
    try:
        run_pipeline()
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("CampScout ETL pipeline completed successfully.")
    print("Build SQLite separately with: python -m db.build_database --reset")
    print("The Streamlit interface is not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
