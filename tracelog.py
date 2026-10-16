"""Trace writer (one JSONL file per run) and the four label rules."""
import json
import time
from pathlib import Path

PRIVATE, UNTRUSTED = "private", "untrusted"
SOURCES = {"read_file": [PRIVATE], "memory": [PRIVATE], "get_website": [UNTRUSTED]}  # rule 1
CLEAN_REPLIES = {"done", "failed"}                                                      # rule 4

events: list[dict] = []
_labels: dict[tuple[str, str], set[str]] = {}
_path: Path | None = None


def start(path: Path | None, **fields) -> dict:
    """Begin a new trace. The first event is 'start' with the run's settings."""
    global _path
    events.clear()
    _labels.clear()
    _path = path
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    return emit("start", **fields)


def emit(kind: str, **fields) -> dict:
    """Append one event. seq is the total order of everything that happened."""
    event = {"seq": len(events), "ts": round(time.time(), 3), "kind": kind, **fields}
    events.append(event)
    if _path:
        with _path.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")
    return event


def labels(agent: str, task: str) -> set[str]:
    """Rule 2: everything the agent received this task. Sticky until the task ends."""
    return _labels.setdefault((agent, task), set())


def receive(agent: str, task: str, new: list[str]) -> None:
    """Add labels to an agent and record a 'label' event whenever its set grows."""
    have = labels(agent, task)
    if set(new) - have:
        have.update(new)
        emit("label", task=task, agent=agent, labels=sorted(have))


def outgoing(agent: str, task: str, text: str) -> list[str]:
    """Rule 3: what an agent sends carries its labels. Rule 4: an exact 'done'/'failed' carries none."""
    return [] if text.strip() in CLEAN_REPLIES else sorted(labels(agent, task))
