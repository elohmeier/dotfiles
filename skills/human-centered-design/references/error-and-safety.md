# Error And Safety

## Treat Error As A System Property

When many people make the same mistake, the design is participating in the failure. Look for conditions that make error likely: ambiguous controls, hidden state, similar actions, interruptions, pressure, weak feedback, mode confusion, and organizational incentives.

## Slips And Mistakes

Slips happen when the goal is right but execution goes wrong. Mistakes happen when the plan or understanding is wrong.

Common slips:

- Capture slip: a familiar routine takes over.
- Description slip: the user acts on a similar-looking target.
- Data-driven slip: visible data accidentally drives the wrong action.
- Associative slip: related thoughts trigger unintended action.
- Loss-of-activation slip: the user forgets the immediate purpose.
- Mode slip: the same action behaves differently in a hidden mode.

Common mistakes:

- Rule-based mistake: a familiar rule is applied in the wrong situation.
- Knowledge-based mistake: the user reasons from incomplete or wrong information.
- Memory-lapse mistake: a necessary step or constraint is forgotten.

Design slips out with better differentiation, undo, confirmation for dangerous actions, mode visibility, and forgiving input. Design mistakes out with clearer models, previews, examples, constraints, and better explanations.

## Prevention Before Warning

Preferred order:

1. Make the dangerous or invalid action impossible.
2. Make the correct action easier and more visible.
3. Require a deliberate sequence for high-risk action.
4. Warn with specific consequences.
5. Provide undo, rollback, or repair.

Warnings alone are weak because people habituate to them, especially under time pressure.

## Forcing Functions

Forcing functions require a necessary condition before action can continue. Use them when risk justifies friction.

Patterns:

- Interlock: action B cannot occur until action A is complete.
- Lock-in: the system keeps an operation active until safe completion.
- Lockout: prevents entry into an unsafe state.
- Confirmation: requires deliberate acknowledgement for irreversible impact.

Keep forcing functions targeted. Broad friction teaches users to bypass safeguards.

## Recovery

A humane design assumes mistakes will happen.

Include:

- Undo for reversible operations.
- Version history for content.
- Soft delete and restore.
- Clear conflict resolution.
- Retry without duplicate side effects.
- Support handoff with diagnostic context.
- Plain-language error messages that preserve entered data.

## Automation Risk

Automation can reduce workload but can also hide state, erode skill, create complacency, and fail in unfamiliar edge cases.

Design automation to:

- Show what it is doing and why.
- Make confidence, uncertainty, and limits visible.
- Let users inspect, correct, override, or stop it.
- Avoid sudden handoff in time-critical moments.
- Preserve human skill for rare but important intervention.
- Log decisions for later review when stakes are meaningful.

## Incident Review

For failures, ask:

- What did the user believe was happening?
- What cues supported that belief?
- What pressures, interruptions, incentives, or constraints shaped action?
- Where did the system allow, invite, or hide the failure?
- What design change would prevent a recurrence or make recovery faster?

Avoid root causes that stop at "user did not read" or "operator error."
