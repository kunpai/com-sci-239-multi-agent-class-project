# Plan: CS239 submission archives

Goal: package HASHIRU-lite in the course's two-archive format.

- **Archive 1** (`KunalPai-hashiru-lite-306152378-requirements.tar.gz`, top folder `hashiru-lite/`): `app.md`,
  `policy.md` (P1–P5 = R1–R5 as numbered paragraphs), `tools.md` (8 tools, one per line), `agents/` (CEO,
  manager, worker; system prompts generated from `agent.system_prompt()`), and `episodes/` (four real runs and
  one hypothetical). Sources live in `submission/hashiru-lite/`.
- **Archive 2** (`...-whole.tar.gz`, top folder `src/`): `git archive` of HEAD, including `submission/`. README
  gains requirements, an env var table, a no-key configuration and a verified example run; `tests/README.md`
  describes every test case.
- `package.py` checks the docs against the code before building: tool names, system prompts, `Pn.`
  numbering, test coverage of `tests/README.md`, and a clean worktree.

Decisions: agents are documented as roles, since they are hired at runtime; `check.py` and `policy.py` are
analysis tools, not agents; the harness guards stay out of policy.md.
