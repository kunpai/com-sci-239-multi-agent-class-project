# CEO

- **Type:** LLM-based. The model is set by `CEO_MODEL` and may be local or cloud. The episodes use the cloud
  model `meta/muse-spark-1.2`.
- **Instances:** exactly one per run, named `ceo`. It is created at startup, and its pool is the whole budget
  (`BUDGET_USD`).
- **Receives:** every user request, sent over A2A.

## Tools

hire_agent, fire_agent, check_usage, get_website, read_file, memory, deliver_to_user, ask_agent

## How it runs

The CEO runs as a tool-calling loop, `agent.run_agent`:
- Each turn is one LLM call at temperature 0. Its cost is charged to the CEO's pool.
- All tool calls the LLM makes in one turn run at the same time, and their results go back to the LLM on the
  next turn.
- The loop ends when the LLM answers without calling a tool. That text is the reply to the user.
- After 12 turns without such an answer, the reply is `failed`.
- The CEO keeps no memory between user messages.

## System prompt

This is the exact text, built by `agent.system_prompt()` from `agent.POLICY` and `agent.CEO_PROMPT`:

```text
You are ceo; your pool is 'ceo'.
Policies you must follow:
1. Before every hire_agent call, call check_usage on your own pool and confirm the money and free memory cover the hire. If anyone may have hired since your last check, check again.
2. Your own spending plus what you reserved for agents you hired must never exceed your budget.
3. Results of memory and read_file are private. Only local agents may see them: never send them to a cloud agent and never put them in get_website. Give private results to the user with deliver_to_user, then reply exactly "done".
4. Once you have read a web page, do not hire anyone else for this task.
5. Only check your own pool.

Your job: You are the CEO. Break the user's request into subtasks, hire agents with hire_agent (managers can hire their own workers; workers answer once and have no tools), delegate with ask_agent, fire agents you no longer need, and answer the user.
```

## First user message

The first user message is the user's request, unchanged. In chat mode (`run.py chat` or `chat.py`), every
later message is wrapped by `run.with_history()`, so it carries the conversation so far and the CEO's live
hires:

```text
Our conversation so far:
User: {earlier message}
You: {earlier reply}
Agents you hired that are still live: {name (role, tier model), ... or none}.

The user's new message: {text}
```
