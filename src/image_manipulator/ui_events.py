"""Typed messages exchanged between UI workers and the main thread."""

from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class StatusEvent:
    text: str


@dataclass(frozen=True)
class CompleteEvent:
    success: int
    total: int
    errors: list[str]
    output_dir: str
    overwrite: bool


@dataclass(frozen=True)
class PreviewEvent:
    generation: int
    image: Image.Image | None
    error: Exception | None


@dataclass(frozen=True)
class UpdateEvent:
    manual: bool
    info: Any | None
    error: str | None


WorkerEvent = StatusEvent | CompleteEvent | PreviewEvent | UpdateEvent
