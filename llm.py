"""Every model call goes through LiteLLM, so any provider can be plugged in."""
import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # use the bundled price map; no network at import

import litellm  # must come after the env var above

litellm.suppress_debug_info = True
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MAX_USD = float(os.environ.get("MAX_USD", "2.00"))
spent_total = 0.0


class WalletExceeded(RuntimeError):
    """Real spend passed MAX_USD. A harness guard that protects the user's money, not a policy."""


def is_local(model: str) -> bool:
    return model.startswith(("ollama_chat/", "ollama/"))


def has_price(model: str) -> bool:
    try:
        litellm.get_model_info(model)
    except Exception:  # noqa: BLE001 - LiteLLM raises a plain Exception for models it has not mapped
        return False
    return True


def check_priced(models: list[str]) -> None:
    """Fail fast: the wallet cap cannot see the cost of an unpriced cloud model."""
    unpriced = [m for m in models if not is_local(m) and not has_price(m)]
    if unpriced:
        raise SystemExit(f"LiteLLM has no price for {unpriced}; add one with litellm.register_model")


async def chat(model: str, messages: list[dict], tools: list[dict] | None = None):
    """One model call at temperature 0. Returns (message, cost_usd).

    The cap is checked before each call, so the call that crosses it is still returned and traced,
    and every later call by any agent is refused.
    """
    global spent_total
    if spent_total > MAX_USD:
        raise WalletExceeded(f"spent ${spent_total:.4f}; the cap is MAX_USD=${MAX_USD}")
    extra = {"api_base": OLLAMA_URL} if is_local(model) else {}
    resp = await litellm.acompletion(model=model, messages=messages, tools=tools or None,
                                     temperature=0, num_retries=2, **extra)  # ride out a 429/503
    cost = 0.0 if is_local(model) else litellm.completion_cost(completion_response=resp)
    spent_total += cost
    return resp.choices[0].message, cost
