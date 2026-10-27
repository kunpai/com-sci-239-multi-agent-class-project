# Worker

- **Type:** LLM-based. Its hirer picks the model from `MODELS`, either local (Ollama) or cloud.
- **Instances:** zero or more per run. The CEO hires them at depth 1, and managers hire them at depth 1 or 2.
- **Receives:** messages from its hirer over `ask_agent`.

## Tools

None

## How it runs

A worker answers each `ask_agent` message with exactly one LLM call:
- The system message is its prompt, the user message is the text it was sent, and no tools are offered.
- The call is charged to the worker's reservation, and the answer goes back to its hirer as the reply.
- The worker keeps no memory between messages.

Workers are not given the policies. With no tools, the only policy a worker's actions bear on is P3. P3 is
checked at the sender: the agent that sends private data to a cloud worker is the one that breaks it.

## System prompt

The system prompt is the hirer's `prompt` argument to `hire_agent`, used verbatim:

```text
{prompt}
```

## Example

This is the full system prompt of `worker_b` in `traces/phase1/s1-20261015-235102.jsonl`. Manager
`managerb` hired it at seq 23 on `ollama_chat/gemma4:latest`:

```text
Compare Python vs Julia for scientific computing. Provide a detailed comparison covering: pros and cons of each language, performance characteristics, ecosystem/tools available, typical use cases, and recommendations for choosing between them. Be thorough and provide actionable insights.
```
