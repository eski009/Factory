# Disk-first reconciliation

Use this protocol when a dispatched child has not returned its reply. The
repository checkpoint and the durable state written after it are the recovery
authority; a missing transport reply is not evidence that the child did no
work.

This protocol covers one parent-child handoff and its current attempt only.
Item 0032 remains responsible for pool exhaustion, `no-synthesis` policy,
whole-fan-out coordination across attempts, and resuming arbitrary prior
council runs.

Resolve the runner exactly as described by `host-adapter.md`. The commands
below use `FACTORY_PLUGIN_ROOT` as the resolved plugin root:

```text
python3 "$FACTORY_PLUGIN_ROOT/scripts/factory/factory.py" --repo . reconcile begin ITEM --stage STAGE --obligation NAME --input PATH... --evidence PATH... [--worktree PATH] --json
python3 "$FACTORY_PLUGIN_ROOT/scripts/factory/factory.py" --repo . reconcile discover ITEM --stage STAGE --obligation NAME --input PATH... [--worktree PATH] --json
python3 "$FACTORY_PLUGIN_ROOT/scripts/factory/factory.py" --repo . reconcile inspect ITEM ATTEMPT --writer-state active|terminal [--worktree PATH] [--claim-continuation] --json
```

`begin` returns the attempt id that belongs to the dispatch. `discover` is for
cold re-entry: reuse an attempt only when exactly one returned id matches the
current item, stage, obligation, inputs, and canonical worktree. Zero matches
means there is no reusable checkpoint. More than one match is ambiguous and
must stop for explicit resolution; never choose the newest-looking attempt.

## One bounded wait and required order

For each dispatch, perform exactly this sequence:

1. Publish the `begin` checkpoint.
2. Dispatch the child whose obligation and evidence paths were checkpointed.
3. Use the host's native wait operation once, capped at 60 seconds.
4. Use the host adapter to establish that exact child's writer state as either
   `active` or `terminal`. No reply alone does not prove terminal state. If the
   host cannot establish either state, stop without inspecting or replacing
   the child.
5. Run `inspect` with that writer state and the same worktree binding, if one
   was checkpointed.
6. Follow exactly one row of the result matrix below: adopt, claim one
   continuation, count a genuine absence, or stop.

An `active` writer returns `still running` from the current stage invocation.
The invocation does not wait a second time, count a failure, claim a
continuation, or dispatch a replacement. A later stage invocation begins by
discovering and inspecting the same attempt again.

## Result matrix

| Classification / action | Required parent behavior |
| --- | --- |
| `complete / adopt` with a terminal writer | Read the durable artifact and continue its normal finalization semantics. |
| `partial / continue` with a terminal writer | Re-run `inspect` through `--claim-continuation`. Dispatch exactly one continuation only when the returned action remains `continue`; `stop` means another parent claimed it or the observation changed. The continuation gets a fresh checkpoint before dispatch. |
| `absent / count-failure` with a terminal writer | Count the one genuine failed attempt through the stage's existing failure path. |
| `partial / wait-active` with an active writer | Return `still running` from this invocation and make no other change. |
| `contradictory / stop` with either writer state | Stop. Do not adopt, claim, count failure, or dispatch a replacement. |

The CLI exits `0` for every valid result, including a valid `stop`; `1` means
malformed arguments or an internal error; `2` means the observed state is
untrusted, stale, contradictory, or has uncertain publication/durability. A
nonzero exit never authorizes a continuation or adoption.

## Transport result is not the verdict

`complete` means only that all declared transport evidence landed or that the
engine recorded the handoff transition. The artifact itself may say PASS,
BLOCK, rejection, or that tests are red. Read it and apply the stage's existing
substantive verdict rules; never convert transport completion into approval.

Before any finalization, re-read the current item stage and the complete
current event log. Perform only the normal side effects that are still
missing. If the child already recorded a legitimate stage transition, adopt
that transition instead of replaying it. Side effects that normally precede a
transition must not be inferred from later state, and post-transition bids or
learning must never be replayed as though they were unfulfilled
pre-transition obligations.
