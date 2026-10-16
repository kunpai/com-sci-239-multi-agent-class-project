"""Who exists and what they hold. Accounting only: nothing here ever blocks."""
import psutil

AGENTS: dict[str, dict] = {}


def add_agent(name: str, role: str, tier: str, model: str, prompt: str,
              parent: str | None, depth: int, reserved: float) -> dict:
    """Register an agent holding a dollar reservation taken from its parent's pool."""
    AGENTS[name] = {"name": name, "role": role, "tier": tier, "model": model, "prompt": prompt,
                    "parent": parent, "depth": depth, "live": True,
                    "reserved": reserved, "spent": 0.0, "gpu_mb": 0}
    return AGENTS[name]


def left(accounts: dict[str, dict]) -> dict[str, float]:
    """Dollars left per agent: reservation minus own spend minus what its children hold.

    A live child holds its reservation; a fired child holds what it spent.
    R2 holds while every value is >= 0.
    """
    def hold(acct: dict) -> float:
        return acct["reserved"] if acct["live"] else acct["spent"]

    return {name: acct["reserved"] - acct["spent"]
            - sum(hold(c) for c in accounts.values() if c["parent"] == name)
            for name, acct in accounts.items()}


def replay(events: list[dict]) -> dict[str, dict]:
    """Rebuild the accounts from a trace, so checks need nothing but the trace.

    A hire_agent event without a result is a proposed hire (Phase 2) and counts as made.
    """
    accounts: dict[str, dict] = {}
    for e in events:
        kind, tool = e["kind"], e.get("name")
        if kind == "start":
            accounts["ceo"] = {"parent": None, "reserved": e["budget_usd"], "spent": 0.0, "live": True}
        elif kind == "llm" and e["agent"] in accounts:
            accounts[e["agent"]]["spent"] += e["cost_usd"]
        elif kind == "tool" and tool == "hire_agent" and "error" not in e.get("result", {}):
            accounts[e["args"].get("name", "?")] = {
                "parent": e["agent"], "reserved": float(e["args"].get("budget_usd", 0)),
                "spent": 0.0, "live": True}
        elif kind == "tool" and tool == "fire_agent":
            for fired in e.get("result", {}).get("fired", []):
                accounts[fired]["live"] = False
    return accounts


def free_mb() -> int:
    """Measured free memory in MB (unified memory on Apple silicon, so it covers the GPU)."""
    return psutil.virtual_memory().available // 2**20
