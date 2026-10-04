"""Run the complete synthetic Milestone 6 example without configuring a model."""

import pytest

from examples.spec_delivery import main


def test_search_handoff_stops_before_implementation(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    output = capsys.readouterr().out
    assert "blocking interface unknown; analytics non-blocking" in output
    assert "answered — gap remains unresolved" in output
    assert "v1 unchanged" in output
    assert "Delivery Gate: passed" in output
    assert "Implementation Authorization: 2 — handoff only" in output
    assert "selected_for_delivery — implementation and outcomes remain deferred" in output
