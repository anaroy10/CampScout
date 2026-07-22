from etl import run_pipeline


def test_pipeline_calls_implemented_phases_and_reports_pending_national_parks(
    monkeypatch, capsys
):
    called = []
    monkeypatch.setattr(
        run_pipeline, "run_activity_cleaning", lambda: called.append("activities")
    )
    monkeypatch.setattr(
        run_pipeline, "run_campground_cleaning", lambda: called.append("campgrounds")
    )

    assert run_pipeline.main([]) == 0

    output = capsys.readouterr().out
    assert called == ["activities", "campgrounds"]
    assert "Activity cleaning phase completed" in output
    assert "Campground cleaning phase completed" in output
    assert "National-park cleaning: not implemented" in output
