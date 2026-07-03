# Scheduled continuous operation

Only useful if scheduled-agent/cron tooling is available; the degraded path — the user manually running `/factory:run loop` whenever they want the factory to advance — is always sufficient and is what continuous operation is written against by default.

## What to schedule

When scheduling tooling is available, put `/factory:autopilot` on the schedule, not `/factory:run loop` directly. Autopilot is the bounded wrapper: it runs a preflight (`factory doctor`, refusing to operate on a corrupt tree), drives the dispatch loop, and stops itself when the backlog drains or a budget is exhausted — properties a bare scheduled `loop` invocation doesn't have on its own. Point the schedule at one autopilot invocation per run; let autopilot's own termination rules decide when that run ends rather than trying to bound it from the scheduler side.

## Cadence

Pick a cadence loose enough that one run reliably finishes (backlog drained or budget spent) before the next one is due — for most repos, something on the order of hourly to a few-times-a-day comfortably clears a single item's worth of pipeline stages without runs piling up on each other. A repo with a thin backlog or infrequent intake needs a slower cadence than one being fed continuously; there's no single correct number, only "slower than the time a typical run takes."

## Safety bounds

Scheduling changes nothing about autopilot's own bounds — it only decides when autopilot gets invoked:

- Autopilot halts on validate errors rather than pushing forward on a broken tree.
- Autopilot respects every configured gate (`merge` policy, human-approval points like `design`'s `waiting-human` pause) exactly as an interactively-run loop would — it never answers its own human gates, it parks items with packets for a person to resolve.
- A run that ends at a gate or a validate error is a normal stopping point, not a failure the schedule needs to work around; the next scheduled invocation simply picks up wherever the backlog left off.

## Degraded path

Without scheduled-agent tooling, none of the above changes — the user runs `/factory:run loop` themselves, as often as they like, and gets the identical bounded behavior autopilot would have applied on a timer. Scheduling only removes the human from having to remember to type the command; it never grants autopilot permission it wouldn't otherwise have.
