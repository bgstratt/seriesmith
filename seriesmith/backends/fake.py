"""
A backend for tests: it records what it is given and plays back a scripted
run, so the queue, the take writer and the editor can be tested without a
GPU or a network.

    fb = FakeBackend(outputs={"9": [("shot.mp4", "video", b"...")]},
                     progress=[0.25, 0.5, 1.0])
    run = fb.submit(graph)
    run.watch(on_progress=...)          # 0.25, 0.5, 1.0, then "succeeded"
    fb.submitted[0]                      # the graph, File inputs as given
"""
from __future__ import annotations

import copy
import itertools
from typing import Callable

from seriesmith.backends import Backend, Output, Progress, Run, files_in

_ids = itertools.count(1)


class FakeRun(Run):
    def __init__(self, backend: "FakeBackend"):
        self.backend = backend.name
        self.id = f"fake-{next(_ids)}"
        self._fb = backend
        self.status = "queued"

    def refresh(self) -> str:
        return self.status

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        if self.status == "queued":
            self.status = "running"
            if on_status:
                on_status("running")
            for v in self._fb.progress:
                if on_progress:
                    on_progress(Progress(v))
            self.status = self._fb.final
            self.error = self._fb.error if self.status != "succeeded" else None
        if on_status:
            on_status(self.status)
        return self.status

    def cancel(self) -> None:
        self.status = "canceled"

    def outputs(self) -> list[Output]:
        if self.status != "succeeded":
            return []
        out = []
        for node, items in self._fb.outputs.items():
            for name, type_, data in items:
                def fetch(path, data=data):
                    with open(path, "wb") as fh:
                        fh.write(data)
                out.append(Output(node, name, type_, fetch))
        return out


class FakeBackend(Backend):
    def __init__(self, name: str = "local", kind: str = "local", *,
                 outputs: dict[str, list[tuple[str, str, bytes]]] | None = None,
                 progress: list[float] | None = None, final: str = "succeeded",
                 error: str | None = "the fake failed", down: str | None = None):
        self.name, self.kind = name, kind
        self.outputs = outputs or {}
        self.progress = [1.0] if progress is None else list(progress)
        self.final, self.error, self.down = final, error, down
        self.submitted: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self.uploaded: list[str] = []

    def ping(self) -> str | None:
        return self.down

    def _upload(self, value):
        v = copy.deepcopy(value)
        for container, key, f in list(files_in(v)):
            self.uploaded.append(f.path)
            container[key] = f
        return v

    def submit(self, graph: dict) -> Run:
        self.submitted.append(self._upload(graph))
        return FakeRun(self)

    def call(self, model: str, arguments: dict) -> Run:
        self.calls.append((model, self._upload(arguments)))
        return FakeRun(self)
