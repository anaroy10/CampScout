from etl import run_pipeline


def test_pipeline_calls_activity_phase_and_reports_pending_phases(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(run_pipeline, "run_cleaning", lambda: called.append(True))

    assert run_pipeline.main([]) == 0

    output = capsys.readouterr().out
    assert called == [True]
    assert "Activity cleaning phase completed" in output
    assert "Campground cleaning: not implemented" in output
    assert "National-park cleaning: not implemented" in output
