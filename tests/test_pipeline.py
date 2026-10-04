"""Unit tests for the pipeline orchestration (Milestone 6, part A)."""

from __future__ import annotations

import pytest

from novacart.pipeline import (
    PipelineContext,
    PipelineError,
    PipelineStep,
    default_steps,
    run_pipeline,
)


def test_default_steps_are_unique_and_in_dependency_order() -> None:
    steps = default_steps()
    keys = [step.key for step in steps]
    assert len(keys) == len(set(keys))
    assert keys[0] == "generate"
    assert keys.index("generate") < keys.index("verify_artifacts")
    assert keys.index("verify_artifacts") < keys.index("postgres")
    assert keys.index("postgres") < keys.index("load_raw")
    assert keys.index("load_raw") < keys.index("raw_checks")
    assert keys.index("raw_checks") < keys.index("analytics_layer")
    assert keys.index("analytics_layer") < keys.index("analytics")
    assert keys.index("analytics") < keys.index("dashboard")
    assert keys.index("dashboard") < keys.index("end_to_end")
    assert keys.index("end_to_end") < keys.index("portfolio")
    assert "tests" not in keys
    assert default_steps(include_tests=True)[-1].key == "tests"


def test_pipeline_runs_every_step_and_records_summaries() -> None:
    calls: list[str] = []

    def make(key: str, summary: str):
        def run(_context: PipelineContext) -> str:
            calls.append(key)
            return summary

        return run

    steps = (
        PipelineStep("a", "First step", make("a", "one")),
        PipelineStep("b", "Second step", make("b", "two")),
        PipelineStep("c", "Third step", make("c", "three")),
    )
    report = run_pipeline(steps=steps)

    assert calls == ["a", "b", "c"]
    assert [result.key for result in report.steps] == ["a", "b", "c"]
    assert [result.summary for result in report.steps] == ["one", "two", "three"]
    assert all(result.seconds >= 0 for result in report.steps)
    assert report.ok is True


def test_pipeline_stops_at_the_first_failure_and_names_the_step() -> None:
    calls: list[str] = []

    def ok(_context: PipelineContext) -> str:
        calls.append("ok")
        return "fine"

    def boom(_context: PipelineContext) -> str:
        calls.append("boom")
        raise ValueError("database is unreachable")

    def never(_context: PipelineContext) -> str:  # pragma: no cover - must not run
        calls.append("never")
        return "unreachable"

    steps = (
        PipelineStep("first", "First step", ok),
        PipelineStep("failing", "Failing step", boom),
        PipelineStep("third", "Third step", never),
    )
    with pytest.raises(PipelineError) as excinfo:
        run_pipeline(steps=steps)

    error = excinfo.value
    assert error.step_key == "failing"
    assert error.step_title == "Failing step"
    assert isinstance(error.cause, ValueError)
    assert "database is unreachable" in str(error)
    assert calls == ["ok", "boom"]  # the third step never ran


def test_pipeline_context_tracks_completed_steps() -> None:
    context = PipelineContext()
    steps = (
        PipelineStep("one", "One", lambda _context: "ok"),
        PipelineStep("two", "Two", lambda _context: "ok"),
    )
    run_pipeline(steps=steps, context=context)
    assert context.completed == ["one", "two"]

