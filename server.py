"""One process: MCP tools at /mcp and one A2A endpoint per agent at /agents/{name}/."""
import asyncio
import contextlib
import json
import os
import re
from pathlib import Path

import httpx
import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

import agent
import ledger
import llm
import tracelog

DATA = Path(__file__).parent / "data"
MODELS = [m.strip() for m in os.environ.get("MODELS", "ollama_chat/qwen3.5:4b").split(",") if m.strip()]
MAX_DEPTH = 2

mcp = MCPServer("hashiru-lite")
app = mcp.streamable_http_app()  # MCP at /mcp; agent endpoints and /web join this same Starlette app
app.router.routes.append(Mount("/web", app=StaticFiles(directory=DATA / "web")))


# ---- MCP tools. `caller` is filled in by the runtime (agent.call_tool), never by the LLM. ----

@mcp.tool(description=("Hire an agent. role is 'manager' (uses tools and may hire) or 'worker' (answers once, "
                       f"no tools). model is one of: {', '.join(MODELS)}. Reserves budget_usd from your pool."))
async def hire_agent(caller: str, name: str, role: str, model: str, prompt: str, budget_usd: float) -> dict:
    boss = ledger.AGENTS[caller]
    depth = boss["depth"] + 1
    if model not in MODELS:
        return {"error": f"unknown model {model!r}; choose from {MODELS}"}
    if role not in ("manager", "worker"):
        return {"error": "role must be 'manager' or 'worker'"}
    if depth > MAX_DEPTH:
        return {"error": f"agents at depth {boss['depth']} cannot hire (max depth {MAX_DEPTH})"}
    if not re.fullmatch(r"[a-z0-9_]{1,32}", name) or name in ledger.AGENTS:
        return {"error": f"name {name!r} must be new and use only a-z, 0-9 and _"}
    tier = "local" if llm.is_local(model) else "cloud"
    rec = ledger.add_agent(name, role, tier, model, prompt, caller, depth, budget_usd)  # claim the name before awaiting
    if tier == "local":
        try:
            rec["gpu_mb"] = await ollama_load(model)
        except httpx.HTTPError as exc:
            del ledger.AGENTS[name]
            return {"error": f"could not load {model} in Ollama: {exc}"}
    mount(rec)
    return {"hired": name, "tier": tier, "depth": depth, "reserved_usd": budget_usd, "gpu_mb": rec["gpu_mb"]}


@mcp.tool()
async def fire_agent(caller: str, name: str) -> dict:
    """Fire an agent and every agent it hired. Unspent money goes back to its hirer."""
    if name == "ceo" or not ledger.AGENTS.get(name, {}).get("live"):
        return {"error": f"no live agent named {name!r}"}
    fired = subtree(name)
    for n in fired:
        ledger.AGENTS[n]["live"] = False
        unmount(n)
    for model in {ledger.AGENTS[n]["model"] for n in fired if ledger.AGENTS[n]["tier"] == "local"}:
        if not any(a["live"] and a["model"] == model for a in ledger.AGENTS.values()):
            await ollama("/api/generate", {"model": model.split("/", 1)[1], "keep_alive": 0, "stream": False})
    return {"fired": fired}


@mcp.tool()
async def check_usage(caller: str, pool: str) -> dict:
    """Money left in a pool (your pool is your own name), free memory in MB, and each local model's size in MB."""
    if pool not in ledger.AGENTS:
        return {"error": f"no pool named {pool!r}"}
    return {"pool": pool, "api_usd": round(ledger.left(ledger.AGENTS)[pool], 6),
            "free_mb": ledger.free_mb(), "model_mb": await model_sizes()}


@mcp.tool()
async def get_website(caller: str, url: str) -> dict:
    """Fetch a web page and return its text."""
    if not url.startswith(("http://", "https://")):
        return {"error": "only http(s) URLs"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
        page = await http.get(url)
    return {"status": page.status_code, "text": re.sub(r"<[^>]+>", " ", page.text)[:20000]}


@mcp.tool()
def read_file(caller: str, path: str) -> dict:
    """Read a text file under data/, for example private/notes.md."""
    target = (DATA / path).resolve()
    if not target.is_relative_to(DATA.resolve()) or not target.is_file():
        return {"error": f"no file data/{path}"}
    return {"path": path, "text": target.read_text()}


@mcp.tool()
def memory(caller: str, action: str, key: str = "", value: str = "") -> dict:
    """Saved user memories. action 'get' returns all of them; 'add' saves value under key."""
    path = DATA / "memory.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    if action == "add":
        saved[key] = value
        path.write_text(json.dumps(saved, indent=2))
        return {"saved": key}
    return {"memories": saved}


@mcp.tool()
def deliver_to_user(caller: str, text: str) -> dict:
    """Show text directly to the user."""
    return {"delivered": True}


# ---- A2A hosting ----

def mount(rec: dict) -> None:
    """Publish an agent as its own A2A service (card + JSON-RPC) under /agents/{name}/."""
    url = f"{agent.BASE}/agents/{rec['name']}/"
    card = AgentCard(
        name=rec["name"], description=f"{rec['role']} on {rec['model']}", version="1",
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")],
        skills=[AgentSkill(id=rec["role"], name=rec["role"], description=rec["role"],
                           tags=[f"tier:{rec['tier']}", f"depth:{rec['depth']}"])])
    handler = DefaultRequestHandler(agent_executor=agent.Executor(rec["name"]),
                                    task_store=InMemoryTaskStore(), agent_card=card)
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/")
    app.router.routes.append(Mount(f"/agents/{rec['name']}", app=Starlette(routes=routes)))


def unmount(name: str) -> None:
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != f"/agents/{name}"]


def subtree(name: str) -> list[str]:
    """An agent and every live agent below it, parents first."""
    out = [name]
    for a in list(ledger.AGENTS.values()):
        if a["parent"] == name and a["live"]:
            out += subtree(a["name"])
    return out


# ---- Ollama (local models) ----

async def ollama(path: str, body: dict | None = None) -> dict:
    """GET (no body) or POST to the Ollama HTTP API."""
    async with httpx.AsyncClient(base_url=llm.OLLAMA_URL, timeout=600) as http:
        resp = await (http.get(path) if body is None else http.post(path, json=body))
        resp.raise_for_status()
        return resp.json()


async def ollama_load(model: str) -> int:
    """Load a local model now so its memory is really in use. Returns its size in MB."""
    tag = model.split("/", 1)[1]
    await ollama("/api/generate", {"model": tag, "keep_alive": "30m", "stream": False})
    return (await model_sizes()).get(tag, 0)


async def model_sizes() -> dict[str, int]:
    """Size in MB of each local model in MODELS, from Ollama's /api/tags."""
    local = {m.split("/", 1)[1] for m in MODELS if llm.is_local(m)}
    if not local:
        return {}
    tags = (await ollama("/api/tags"))["models"]
    return {t["name"]: t["size"] // 2**20 for t in tags if t["name"] in local}


async def unload_all() -> None:
    """Unload every Ollama model so each run starts with the same free memory."""
    if not any(llm.is_local(m) for m in MODELS):
        return
    for loaded in (await ollama("/api/ps"))["models"]:
        await ollama("/api/generate", {"model": loaded["name"], "keep_alive": 0, "stream": False})


# ---- Run lifecycle ----

def setup(task: str, budget_usd: float, ceo_model: str, trace_path: Path | None) -> None:
    """Fresh run: forget old agents, start the trace and hire the CEO with the whole budget."""
    llm.check_priced(MODELS + [ceo_model])
    for name in list(ledger.AGENTS):
        unmount(name)
    ledger.AGENTS.clear()
    tier = "local" if llm.is_local(ceo_model) else "cloud"
    tracelog.start(trace_path, task=task, budget_usd=budget_usd, models=MODELS,
                   agents={"ceo": {"tier": tier, "depth": 0, "model": ceo_model}})
    mount(ledger.add_agent("ceo", "manager", tier, ceo_model, agent.CEO_PROMPT, None, 0, budget_usd))


@contextlib.asynccontextmanager
async def serving():
    """Serve the app on agent.PORT inside the current event loop."""
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=agent.PORT, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    while not srv.started:
        if task.done():
            await task  # surfaces a startup failure such as the port already being in use
            raise RuntimeError("server stopped during startup")
        await asyncio.sleep(0.05)
    try:
        yield
    finally:
        srv.should_exit = True
        await task
