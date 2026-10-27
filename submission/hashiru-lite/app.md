# HASHIRU-lite

HASHIRU-lite is a hierarchical multi-agent orchestrator, a minimal version of HASHIRU
([Pai et al., 2025](https://arxiv.org/abs/2506.04255)). The user talks to one CEO agent. The CEO splits the
request into subtasks, hires other agents while it runs and pays for each one out of a fixed budget, delegates
to them, and answers the user.

## Tasks it supports

- **General requests handled by a team:** comparisons, research questions, summaries and writing. The CEO
  decides whether to answer itself or to hire managers and workers, and on which models.
- **Tasks over the user's personal data:** agents can read the user's saved memories (`memory`) and private
  files under `data/` (`read_file`), for example to build a study plan around the user's schedule.
- **Web tasks:** agents can fetch and summarize a web page (`get_website`).
- **Multi-turn chat** with the CEO, in the terminal or in a browser. Agents hired in one turn stay hired for
  later turns.

## How it works

- **Agents.** There are three roles, each LLM-based, with one file per role in `agents/`:
  - **CEO:** always present. It receives every user request and holds the whole budget.
  - **Manager:** hired at runtime. It uses tools and may hire workers out of its own reservation.
  - **Worker:** hired at runtime. It answers once and has no tools.
- **Coordination.** Centralized and hierarchical, with dynamic interactions:
  - The CEO picks at runtime how many agents to hire, in which roles and on which models.
  - Every agent has exactly one hirer. It may message only agents it hired and fire only agents below it.
  - Hiring stops 2 levels below the CEO.
- **Local or cloud.** Each hire runs either on a local Ollama model, which uses machine memory, or on a cloud
  model through LiteLLM, which costs API dollars. `check_usage` reports both.
- **Protocols.**
  - Tools are served over MCP at `/mcp`. Each MCP tool also takes a `caller` argument, which the runtime fills
    in; the LLM never sees it.
  - Each agent is its own A2A service at `/agents/{name}/`, and agents message each other with `ask_agent`
    over A2A.
- **Entry point.** The CEO is the only entry point:
  - `run.py <scenario>` sends it one fixed request.
  - `run.py chat` (terminal) and `chat.py` (browser) let the user chat with it.
- **Trace.** Every LLM call, tool call and message passes through `agent.py`, which writes it to a JSONL
  trace.
  - The trace also records labels: `memory` and `read_file` results are `private`, and `get_website` results
    are `untrusted`.
  - An agent holds every label it has received during the task, and everything it sends carries them.

## Policies

`policy.md` states five policies, P1–P5:
- **How agents learn them:** in this version they are prompt text in the CEO's and managers' system prompts.
- **Enforcement:** nothing blocks a violating action.
- **How violations are found:** `check.py` (built on `policy.py`) replays a trace and reports every violation,
  and the trace viewer (`viewer.py`) marks them in red. Both are offline analysis tools, not agents.

`check.py` reports each policy under its ID in `requirements.md`, so a P1 violation prints as `R1`.

The episodes in `episodes/` come from real traces shipped in the whole archive under `src/traces/`. The
exception is `example4`, which is hypothetical.
