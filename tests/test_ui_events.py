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
import threading
from types import SimpleNamespace

import pytest
from PIL import Image

pytest.importorskip("tkinter")

from image_manipulator import ui
from image_manipulator.pipeline import ImageManipulator
from image_manipulator.ui_events import CompleteEvent, StatusEvent


class _PoisonEvent:
    """Event that makes the dispatcher raise."""


class _EventRecorder:
    """Stand-in exposing just what ``_drain_events`` touches."""

    def __init__(self):
        self._events = queue.Queue()
        self.applied = []

    def _dispatch_event(self, event):
        if isinstance(event, _PoisonEvent):
            raise RuntimeError("handler blew up")
        self.applied.append(event)


class TestEventDrain:
    def test_one_bad_event_does_not_stop_the_others(self, caplog):
        app = _EventRecorder()
        app._events.put(_PoisonEvent())
        app._events.put(StatusEvent("Processing 1/2: a.png"))
        app._events.put(CompleteEvent(2, 2, [], "/tmp", False))

        with caplog.at_level(logging.ERROR, logger=ui.logger.name):
            ui.ManipulatorApp._drain_events(app)

        assert app.applied == [
            StatusEvent("Processing 1/2: a.png"),
            CompleteEvent(2, 2, [], "/tmp", False),
        ]
        assert "Failed to apply event" in caplog.text

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

        assert [(ms, cb.__name__) for ms, cb in scheduled] == [(100, "_poll_events")]
        assert "Event polling failed" in caplog.text


class TestUnexpectedWorkerFailure:
    def test_failure_is_reported_in_the_completion_event(self, caplog):
        class BrokenManipulator:
            def process_path(self, *args, **kwargs):
                raise RuntimeError("boom")

        app = SimpleNamespace(_events=queue.Queue(), _cancel_event=threading.Event())

        with caplog.at_level(logging.ERROR, logger=ui.logger.name):
            ui.ManipulatorApp._process_worker(
                app, ["a.png", "b.png"], BrokenManipulator(), "/tmp", False
            )

        events = []
        while not app._events.empty():
            events.append(app._events.get_nowait())
        completes = [event for event in events if isinstance(event, CompleteEvent)]

        assert len(completes) == 1
        complete = completes[0]
        assert (complete.success, complete.total) == (0, 2)
        assert complete.errors
        assert "boom" in complete.errors[0]
        assert (complete.output_dir, complete.overwrite) == ("/tmp", False)
        assert "Batch worker stopped early" in caplog.text


class TestPreviewWorker:
    def test_worker_posts_the_rendered_image(self):
        image = Image.new("RGB", (32, 24), "red")

        class StubManipulator:
            def render(self, source):
                return source.copy()

        app = SimpleNamespace(_events=queue.Queue())

        ui.ManipulatorApp._preview_worker(app, 4, StubManipulator(), image)

        event = app._events.get_nowait()
        assert event.generation == 4
        assert event.image.size == image.size
        assert event.error is None

    def test_worker_posts_an_error_instead_of_raising(self):
        class BrokenManipulator:
            def render(self, source):
                raise RuntimeError("preview failed")

        app = SimpleNamespace(_events=queue.Queue())

        ui.ManipulatorApp._preview_worker(
            app, 2, BrokenManipulator(), Image.new("RGB", (8, 8))
        )

        event = app._events.get_nowait()
        assert event.generation == 2
        assert event.image is None
        assert isinstance(event.error, RuntimeError)

    def test_stale_preview_is_ignored(self):
        shown = []

        class StubVar:
            def set(self, value):
                pass

        app = SimpleNamespace(
            _preview_generation=5,
            output_size_var=StubVar(),
            status_var=StubVar(),
            _show_image=lambda image: shown.append(image),
        )
        image = Image.new("RGB", (8, 8), "red")

        ui.ManipulatorApp._on_preview_ready(app, 4, image, None)
        assert shown == []

        ui.ManipulatorApp._on_preview_ready(app, 5, image, None)
        assert shown == [image]


class TestCloseDuringBatch:
    @staticmethod
    def _app():
        destroyed = []

        class StubRoot:
            def destroy(self):
                destroyed.append(True)

        app = SimpleNamespace(
            _processing=True,
            _cancel_event=threading.Event(),
            root=StubRoot(),
            _cancel_scheduled_preview=lambda: None,
            _cancel_scheduled_settings_save=lambda: None,
            _save_settings_now=lambda: None,
        )
        return app, destroyed

    def test_cancelled_confirmation_keeps_the_window_open(self, monkeypatch):
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **_: False)
        app, destroyed = self._app()

        ui.ManipulatorApp._on_close(app)

        assert destroyed == []
        assert app._cancel_event.is_set() is False

    def test_confirmed_close_cancels_the_worker_and_destroys_the_window(
        self, monkeypatch
    ):
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **_: True)
        app, destroyed = self._app()

        ui.ManipulatorApp._on_close(app)

        assert app._cancel_event.is_set() is True
        assert destroyed == [True]


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
        app = SimpleNamespace(_events=queue.Queue(), _cancel_event=threading.Event())

        for _ in range(2):
            ui.ManipulatorApp._process_worker(
                app, sources, manipulator, str(output), False
            )

        events = []
        while not app._events.empty():
            events.append(app._events.get_nowait())
        statuses = [e for e in events if isinstance(e, StatusEvent)]
        completes = [e for e in events if isinstance(e, CompleteEvent)]

        # A repeated batch run is a full pass: per-item progress both times,
        # a completion event for every run, and new results that never
        # replace the previous run's files.
        assert len(statuses) == 6
        assert [e.success for e in completes] == [3, 3]
        assert len(list(output.iterdir())) == 6
