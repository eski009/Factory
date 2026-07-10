# Focus-group templates and caps

Output contracts for the focus-group step (`factory-research` §3b). Caps are hard: 4–6 personas; guide ≤500 words and ≤10 questions; findings ≤5 bullets per persona plus exactly one `## Synthesis` paragraph and one `## Next action` line. All artifacts live under
`.factory/runs/research/focus-group/<YYYY-MM-DD>/` (same-day re-runs suffix
`-2`, `-3`, …). Interview-derived claims always carry the citation class
`(simulated: focus-group run <date>)` — never fact-grade `(source:)`.

## Roster template

`roster.md` — 4–6 entries spanning at least two distinct classes.

```markdown
# Focus-group roster — run <date>

## <Persona label>
- **Label:** <short name, e.g. "Procurement officer">
- **Class:** <one of: sme | customer | buyer | decision-maker | influencer>
- **Relationship:** <one line: how this stakeholder relates to the product>
- **Can credibly inform:** <what a simulation of this persona can usefully
  hypothesize about>
- **Cannot credibly inform:** <what it cannot — e.g. a simulated child
  cannot inform real usability>
- **Rationale:** <one line, `(source: <seed passage>)` where derived from a
  real input, `(assumption)` otherwise>
```

## Interview guide template

`guides/<persona-slug>.md` — ≤500 words, ≤10 questions, one per persona.
Guides are **human-usable as-is**: the interviewer-facing text contains
no AI, roleplay, or meta instructions — a human can read one verbatim to a
real person.

```markdown
# Interview guide — <Persona label>

<2–3 sentence interviewer intro script: who we are, what we're exploring,
how their answers will be used.>

1. <open-ended question 1>
2. <open-ended question 2>
   … (6–10 ordered, open-ended questions total)

<one-line close: thanks + what happens next.>
```

## Transcript template

`transcripts/<persona-slug>.md` — one simulated interview per persona, one
round, no follow-ups. Slug must match the guide's.

```markdown
> This transcript is an AI-roleplayed simulation, not user evidence.
> Citation class: (simulated: focus-group run <date>).

# Simulated interview — <Persona label> — run <date>

**Q1.** <guide question 1>
**A1.** <in-character answer>
… (one Q/A pair per guide question, numbered to match)
```

## Findings template

`findings.md` — per persona ≤5 bullets, each ending with the citation
class; then exactly one `## Synthesis` paragraph and one `## Next action`
line (copy-pasteable).

```markdown
> Assumption-grade by construction (see docs/factory/brain/constraints.md):
> simulated output may never be cited as (source:), is mirrored to
> open-questions.md, and can never resolve the persona-validation open
> question.

# Focus-group findings — run <date>

## <Persona label>
- <finding> (simulated: focus-group run <date>)
  … (≤5 bullets per persona)

## Synthesis
<exactly one paragraph>

## Next action
Take the guides in `.factory/runs/research/focus-group/<date>/guides/` to
real humans matching the roster.
```

## Spend log template

`spend.md` — the run's own token/effort log, quoted in the Exit report and
any autopilot packet.

```markdown
# Focus-group spend — run <date>

- run date: <date>
- trigger: <deep | --focus-group>
- persona count: <n>
- subagent count: <n>
- timestamps: <start> → <end>
- token counts: <per-interview + total, where the harness exposes them;
  otherwise the explicit line:>
  token counts: UNMEASURED this run (effort proxies only)
- effort proxies: <subagent count, total transcript word count>
```
