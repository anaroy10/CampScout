from etl import run_pipeline


def test_pipeline_calls_all_phases_in_dependency_order(monkeypatch, capsys, tmp_path):
    called = []
    monkeypatch.setattr(run_pipeline, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(run_pipeline, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(
        run_pipeline, "run_activity_cleaning", lambda: called.append("activities")
    )
    monkeypatch.setattr(
        run_pipeline, "run_campground_cleaning", lambda: called.append("campgrounds")
    )
    monkeypatch.setattr(run_pipeline, "run_park_cleaning", lambda: called.append("parks"))
    monkeypatch.setattr(
        run_pipeline, "run_distance_calculation", lambda: called.append("distances")
    )

    assert run_pipeline.main([]) == 0

    output = capsys.readouterr().out
    assert called == ["activities", "campgrounds", "parks", "distances"]
    assert (tmp_path / "processed").is_dir()
    assert (tmp_path / "reports").is_dir()
    assert "Starting activity cleaning phase" in output
    assert "Completed distance calculation phase" in output
    assert "pipeline completed successfully" in output
    assert "python -m db.build_database --reset" in output
    assert "python -m streamlit run streamlit_app.py" in output


def test_pipeline_stops_and_returns_nonzero_when_a_phase_fails(
    monkeypatch, capsys, tmp_path
):
    called = []
    monkeypatch.setattr(run_pipeline, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(run_pipeline, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(
        run_pipeline, "run_activity_cleaning", lambda: called.append("activities")
    )

    def fail_campgrounds():
        called.append("campgrounds")
        raise run_pipeline.CampgroundCleaningError("validation failed")

    monkeypatch.setattr(run_pipeline, "run_campground_cleaning", fail_campgrounds)
    monkeypatch.setattr(run_pipeline, "run_park_cleaning", lambda: called.append("parks"))
    monkeypatch.setattr(
        run_pipeline, "run_distance_calculation", lambda: called.append("distances")
    )

    assert run_pipeline.main([]) == 1
    captured = capsys.readouterr()
    assert called == ["activities", "campgrounds"]
    assert "Pipeline failed during campground cleaning" in captured.err
