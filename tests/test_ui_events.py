"""Headless regression tests for the batch event plumbing.

The second "Process All" run used to freeze the UI: an exception raised
from inside the polling callback (a message dialog dying in
``wait_visibility``) stopped the event loop forever, so progress and
completion events were never applied again — the status bar stayed at
"Processing..." and the button stayed disabled. These tests need no
display.
"""

import logging
import queue
from types import SimpleNamespace

import pytest
from PIL import Image

pytest.importorskip("tkinter")

from image_manipulator import ui  # noqa: E402
from image_manipulator.pipeline import ImageManipulator  # noqa: E402


class _EventRecorder:
    """Stand-in exposing just what ``_drain_events`` touches."""

    def __init__(self):
        self._events = queue.Queue()
        self.applied = []

    def _dispatch_event(self, event):
        if event[0] == "poison":
            raise RuntimeError("handler blew up")
        self.applied.append(event)


class TestEventDrain:
    def test_one_bad_event_does_not_stop_the_others(self, caplog):
        app = _EventRecorder()
        app._events.put(("poison",))
        app._events.put(("status", "Processing 1/2: a.png"))
        app._events.put(("complete", 2, 2, [], "/tmp", False))

        with caplog.at_level(logging.ERROR, logger=ui.logger.name):
            ui.ManipulatorApp._drain_events(app)

        assert app.applied == [
            ("status", "Processing 1/2: a.png"),
            ("complete", 2, 2, [], "/tmp", False),
        ]
        assert "poison" in caplog.text

    def test_drain_returns_normally_when_the_queue_is_empty(self):
        app = _EventRecorder()

        ui.ManipulatorApp._drain_events(app)  # must not raise

        assert app.applied == []


class TestPollLoop:
    def test_keeps_rescheduling_after_a_failure(self, caplog):
        scheduled = []

        class StubRoot:
            def after(self, ms, callback):
                scheduled.append((ms, callback))

        class StubApp:
            root = StubRoot()

            def _drain_events(self):
                raise RuntimeError("drain exploded")

            def _poll_events(self):  # the reschedule target
                pass

        with caplog.at_level(logging.ERROR, logger=ui.logger.name):
            ui.ManipulatorApp._poll_events(StubApp())  # must not raise

        assert [(ms, cb.__name__) for ms, cb in scheduled] == [
            (100, "_poll_events")
        ]
        assert "Event polling failed" in caplog.text


class TestSecondBatchRun:
    def test_processes_and_reports_completion_every_run(self, tmp_path):
        sources = []
        for index in range(3):
            path = tmp_path / f"source{index}.png"
            Image.new("RGB", (48, 36), (index * 50, 90, 140)).save(path)
            sources.append(str(path))
        output = tmp_path / "output"
        output.mkdir()
        manipulator = ImageManipulator(target_width=24, target_height=18)
        app = SimpleNamespace(_events=queue.Queue())

        for _ in range(2):
            ui.ManipulatorApp._process_worker(
                app, sources, manipulator, str(output), False
            )

        events = []
        while not app._events.empty():
            events.append(app._events.get_nowait())
        statuses = [e for e in events if e[0] == "status"]
        completes = [e for e in events if e[0] == "complete"]

        # A repeated batch run is a full pass: per-item progress both times,
        # a completion event for every run, and new results that never
        # replace the previous run's files.
        assert len(statuses) == 6
        assert [e[1] for e in completes] == [3, 3]
        assert len(list(output.iterdir())) == 6
