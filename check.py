"""Check traces against R1-R5. Analysis only: nothing is blocked.

Usage: uv run check.py traces/phase1/*.jsonl
"""
import json
import sys
from pathlib import Path

import policy


def check(events: list[dict]) -> list[tuple[int, str]]:
    """(seq, reason) for every violation in a trace, in order."""
    return [(e["seq"], why) for i, e in enumerate(events) for why in policy.violations(events[:i], e)]


def main(paths: list[str]) -> int:
    failed = 0
    for path in paths:
        events = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        found = check(events)
        failed += bool(found)
        print(f"{path}: {'satisfied' if not found else f'{len(found)} violation(s)'}")
        for seq, why in found:
            print(f"  seq {seq}: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
