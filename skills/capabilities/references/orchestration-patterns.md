# Orchestration patterns

These patterns assume nothing about the orchestrating model — they are how the factory gets strong-model outcomes from any model. They were not designed in the abstract: every one of them is a rule this repo's own build broke, once, and paid for. Read each as name / rule / why / tell: the tell is what you'd notice in the moment you're about to violate it.

## 1. Plans carry complete code

**Rule:** a plan task is done when implementation is transcription — exact code, exact tests, exact commands, expected output. Not "implement the validator," but the validator's body, the test that pins its behavior, and the command that runs it.

**Why:** implementer model quality stops mattering when there is nothing left to invent. This repo's engine code, across every phase, was produced by cheap-tier implementers precisely because the plans left no design decisions in the implementer's hands — only typing. The one time a plan's expected output was itself wrong (a test asserting the wrong exit code), the implementer caught it not by being clever but by following the standing instruction to never weaken a test to make it pass — refusing the mismatch surfaced the plan bug immediately instead of burying it in a silently-adjusted assertion.

**Tell:** a task description that says "add appropriate handling for X" or leaves a code block with a comment instead of a body. If the implementer has to decide *what* to write rather than *where* to put it, the plan isn't done — the planning model just handed its job to a weaker one.

## 2. Fresh subagent per task; report files over pasted context

**Rule:** each task gets exactly its brief plus the interfaces it touches — no session history, no "as discussed above," no accumulated chat transcript. Findings and results cross task boundaries as written files, not as context carried in a long-lived conversation.

**Why:** a subagent that inherits an entire session's scar tissue also inherits its blind spots, its half-abandoned approaches, and its drift from the spec. A fresh dispatch per task forces every task's brief to be self-contained and re-readable — which is also what makes the plan auditable later.

**Tell:** a task brief that says "use the approach we settled on" instead of stating the approach; a dispatch that pastes in a wall of prior conversation instead of pointing at a file.

## 3. Independent task review with two verdicts, then fix → re-review

**Rule:** every task gets a review pass independent of the implementer, and that review renders two separate verdicts — spec compliance and quality — not one blended judgment. A rejection triggers a fix, and the fix always gets a re-review; there is no "the fix was obviously right, skip it." The one exception: for a single-line/single-purpose fix with test evidence attached, the controller's own diff-read stands in for that re-review (pattern 6) — everything else still gets a full re-review.

**Why:** spec compliance and quality fail independently — code can satisfy every acceptance criterion and still be a mess worth flagging, or read cleanly and quietly miss a criterion. Collapsing them into one verdict lets either failure mode hide behind the other. And a fix that isn't re-reviewed is a review gate with a hole in it: the one case most likely to introduce a new bug — a just-edited diff — is the one case skipping re-review leaves unchecked.

**Tell:** a review report with a single "LGTM" instead of two separate calls; a fix applied and immediately advanced without anyone looking at the new diff.

## 4. Adversarial whole-branch review before ship

**Rule:** after every task has passed its own gate, run one more review — ideally with the most capable model available — that walks the entire branch's change end-to-end: trace one real flow across every layer it touches (entry point → data → output), rather than reading the diff top to bottom in commit order.

**Why:** per-task review structurally cannot see integration failures, because no single task's diff contains the seam between tasks. Across this repo's own build, whole-branch review — and specifically walking a flow rather than skimming the diff — is what caught what per-task review missed every single time: a design gate that would regenerate forever, council agents instructed to write files with tools that were read-only, contradictory human-facing instructions spread across three separate files, and a validator that crashed on input its own CLI could produce. In every one of those cases, every per-task review along the way had already passed. Reading the diff linearly reproduces the same blind spot the task reviews had; only tracing a concrete flow through the finished branch — following one real item's ui piece across engine and prose, say — surfaces a seam none of the task-sized views could show.

**Tell:** a final review whose notes read like a diff summary in file order instead of naming the flow it traced; running this step only when task reviews found problems (it matters most when they were clean — clean per-task reviews are exactly the condition under which integration failures survive undetected).

## 5. Batch fix waves

**Rule:** when a review (task-level or whole-branch) produces multiple findings, gather the complete list and hand it to one fixer in one dispatch — never spin up a separate fixer per finding.

**Why:** a per-finding fixer rebuilds the same context — reads the same files, re-derives the same understanding of the change — for every finding, and pays that cost again and again. One fixer with the complete list pays it once and can also see when two findings share a root cause, which per-finding dispatch never notices. This is also why audits should be finished before fixing starts: an audit that reports a partial list and triggers a fix wave, then a second partial list and a second wave, multiplies the same overhead the batching was meant to avoid.

**Tell:** dispatching a new fixer per bullet point in a findings list; starting a fix wave before an audit or review round has finished enumerating everything it found.

## 6. Controller verification for small fixes

**Rule:** when a fix is small — a one-line change with test evidence attached — the orchestrating session verifies it directly by reading the diff, rather than routing it through another review round-trip. For a single-line/single-purpose fix with test evidence, this diff-read *is* the re-review pattern 3 requires, not a shortcut around it — and the substitution only holds if the diff clears a checklist: (a) the diff implements exactly the specified fix and nothing else; (b) the test evidence names the command run and its output; (c) the covering test actually exercises the changed line. Anything failing the checklist routes to a normal re-review.

**Why:** review capacity is finite and should go where judgment is actually needed. A one-sentence fix with a passing test attached is faster and just as reliably checked by the controller reading the diff itself; running it through a full review cycle anyway doesn't buy more confidence, it just spends a review slot on a change too small to need one.

**Tell:** dispatching a review subagent for a change you could read yourself in the time it takes to write the dispatch; conversely, waving through a multi-file fix without reading it because "it's just a fix" — that's the same pattern misapplied to something that actually needed judgment.

## 7. Evidence before assertion

**Rule:** nothing is "done," "fixed," or "passing" without the command output that shows it. A refusal to proceed must name specifically what's missing, not gesture at a general concern.

**Why:** a claim without a command behind it is a guess wearing a verdict. This repo's independent audits held to this by re-running the exploit itself rather than trusting a fix report that said it was resolved, and its re-reviews verified fixes by replaying the original exploit, not by reading the fixer's description of what changed. That's the whole pattern: don't trust a description of a test result, produce the test result.

**Tell:** a status update that says "should be fixed now" or "this looks correct" with no command transcript attached; a re-review that reads the fix's own summary instead of re-running the thing the fix was supposed to fix.

## See also

`references/model-tiering.md` — which tier of model each of these patterns needs (transcription-tier implementers depend on pattern 1 being followed to the letter; pattern 4's whole-branch walk depends on the most-capable tier being the one doing it).
