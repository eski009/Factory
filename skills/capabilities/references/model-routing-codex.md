# Model routing for Codex

This resolves the abstract tiers in `model-tiering.md` for the current Codex
fleet. It is a default policy, not permission to spend indiscriminately. Keep a
capable model already running in the host when it meets or exceeds the route;
do not relaunch merely to match a label.

| Factory work | Codex model | Reasoning effort | Why |
|---|---|---|---|
| Pipeline orchestration, status, file routing | `gpt-5.6-terra` | `medium` | Reliable coordination at lower cost |
| Mechanical commands or a fully specified tiny edit | `gpt-5.6-terra` | `low` or `medium` | Little ambiguity; verify the result |
| Routine bug fix or bounded implementation | `gpt-5.6-terra` | `high` | Strong implementation without flagship cost |
| Complex implementation, refactor, architecture-sensitive change | `gpt-5.6-sol` | `high` | Quality matters more than throughput |
| Product design, spec, plan, architecture judgement | `gpt-5.6-sol` | `high` | Requires synthesis and trade-off reasoning |
| Independent review, council synthesis, journey assurance | `gpt-5.6-sol` | `xhigh` | Adversarial evaluation is the quality floor |

Use `max` only for an exceptional, high-consequence adjudication after `xhigh`
has proved insufficient. Do not make `max` or `ultra` a repository-wide
default. Begin with the table's effort, measure quality, and test the same or
one lower effort on repeatable work before spending more.

## Independence

Prefer a fresh context for every reviewer. For ordinary implementation, the
strongest economical split is Terra `high` to implement and Sol `xhigh` to
review or assure. When the change genuinely requires Sol `high` to implement,
review in a fresh Sol `xhigh` context and disclose that model diversity was not
available; never pretend an effort change is a different model.

For a headless Codex worker, configure the defaults in `.factory/config.json`:

```json
{
  "workers": {
    "backend": "codex",
    "models": {"codex": "gpt-5.6-terra"},
    "codex": {"reasoning_effort": "high"}
  }
}
```

The per-run override is `factory work ITEM --model MODEL
--reasoning-effort EFFORT`.
