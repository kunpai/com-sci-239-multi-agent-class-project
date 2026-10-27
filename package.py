"""Build the two CS239 submission archives into dist/, after checking the docs against the code.

Usage: uv run package.py                 # dist/KunalPai-hashiru-lite-306152378-requirements.tar.gz and ...-whole.tar.gz
       uv run package.py --name X --uid Y

Archive 1 (requirements) is submission/<app>/ (app.md, policy.md, tools.md, agents/, episodes/).
Archive 2 (whole) is every committed file under src/: code, requirements, tests and traces. It comes from
HEAD, so commit first.
"""
import argparse
import asyncio
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import agent
import server

ROOT = Path(__file__).parent


def problems(app_dir: Path) -> list[str]:
    """Everything that would make the submission disagree with the code or the course format."""
    found = [f"missing {p}" for p in ("app.md", "policy.md", "tools.md") if not (app_dir / p).is_file()]
    found += [f"no files in {d}/" for d in ("agents", "episodes") if not list((app_dir / d).glob("*.md"))]
    if found:
        return found

    lines = [line for line in (app_dir / "tools.md").read_text().splitlines() if line.strip()]
    named = [m.group(1) for line in lines if (m := re.match(r"([a-z_]+): \S", line))]
    if len(named) != len(lines):
        found.append("tools.md: every line must be 'tool_name: description'")
    real = {t.name for t in asyncio.run(server.mcp.list_tools())} | {"ask_agent"}
    if set(named) != real:
        found.append(f"tools.md lists {sorted(set(named))} but the code has {sorted(real)}")

    paragraphs = [p.strip() for p in (app_dir / "policy.md").read_text().split("\n\n") if p.strip()]
    if len(paragraphs) < 3 or any(not p.startswith(f"P{i}. ") for i, p in enumerate(paragraphs, 1)):
        found.append("policy.md: need at least 3 paragraphs numbered P1., P2., ... in order")

    ceo = agent.system_prompt({"role": "manager", "name": "ceo", "prompt": agent.CEO_PROMPT})
    template = agent.system_prompt({"role": "manager", "name": "{name}", "prompt": "{prompt}"})
    for file, prompt in (("ceo.md", ceo), ("manager.md", template)):
        if prompt not in (app_dir / "agents" / file).read_text():
            found.append(f"agents/{file} does not contain the system prompt that agent.py builds")

    described = (ROOT / "tests" / "README.md").read_text()
    tests = {m for f in (ROOT / "tests").glob("test_*.py")
             for m in re.findall(r"^def (test_\w+)", f.read_text(), re.MULTILINE)}
    missing = sorted(t for t in tests if f"`{t}`" not in described)
    if missing:
        found.append(f"tests/README.md does not describe {missing}")

    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout
    if dirty:
        found.append("uncommitted changes: the whole archive is built from HEAD, so commit them first")
    return found


def build(name: str, uid: str, app: str, out: Path) -> tuple[Path, Path]:
    out.mkdir(exist_ok=True)
    docs, src = out / f"{name}-{app}-{uid}-requirements.tar.gz", out / f"{name}-{app}-{uid}-whole.tar.gz"
    with tarfile.open(docs, "w:gz") as tar:
        tar.add(ROOT / "submission" / app, arcname=app, filter=lambda t: None if t.name.endswith(".DS_Store") else t)
    subprocess.run(["git", "archive", "--format=tar.gz", "--prefix=src/", "-o", str(src), "HEAD"],
                   cwd=ROOT, check=True)
    return docs, src


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="KunalPai")
    parser.add_argument("--uid", default="306152378")
    parser.add_argument("--app", default="hashiru-lite")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    found = problems(ROOT / "submission" / args.app)
    for p in found:
        print(f"error: {p}")
    if found:
        return 1
    for path in build(args.name, args.uid, args.app, args.out):
        with tarfile.open(path) as tar:
            print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {len(tar.getnames())} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
