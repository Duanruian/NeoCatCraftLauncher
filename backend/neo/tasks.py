from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .events import EventBus, make_event


@dataclass
class Task:
    id: str
    kind: str
    title: str
    state: str = "running"
    progress: int = 0
    total: int = 0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data["percent"] = round(self.progress / self.total * 100, 1) if self.total else 0.0
        return data


class TaskManager:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._tasks: dict[str, Task] = {}
        self._last_publish: dict[str, float] = {}

    def create(self, kind: str, title: str, total: int = 0) -> Task:
        task = Task(id=uuid.uuid4().hex[:12], kind=kind, title=title, total=total)
        self._tasks[task.id] = task
        self._trim()
        self._publish(task, force=True)
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list(self) -> list[dict[str, Any]]:
        return [task.snapshot() for task in sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)]

    def update(self, task_id: str, force: bool = False, **fields: Any) -> Task | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = time.time()
        self._publish(task, force=force)
        return task

    def finish(self, task_id: str, result: dict[str, Any] | None = None, message: str = "") -> Task | None:
        return self.update(task_id, force=True, state="done", result=result or {}, message=message)

    def fail(self, task_id: str, error: str) -> Task | None:
        return self.update(task_id, force=True, state="error", error=error, message=error)

    def progress(self, task_id: str, progress: int | None = None, total: int | None = None, message: str | None = None) -> None:
        fields: dict[str, Any] = {}
        if progress is not None:
            fields["progress"] = max(0, progress)
        if total is not None and total > 0:
            fields["total"] = total
        if message is not None:
            fields["message"] = message
        self.update(task_id, **fields)

    def _publish(self, task: Task, force: bool = False) -> None:
        now = time.time()
        last = self._last_publish.get(task.id, 0.0)
        if not force and now - last < 0.12:
            return
        self._last_publish[task.id] = now
        self.bus.publish(make_event("task", task=task.snapshot()))

    def _trim(self) -> None:
        finished = [t for t in self._tasks.values() if t.state != "running"]
        if len(finished) <= 40:
            return
        finished.sort(key=lambda t: t.updated_at)
        for task in finished[: len(finished) - 40]:
            self._tasks.pop(task.id, None)
            self._last_publish.pop(task.id, None)
