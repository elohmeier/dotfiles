# Action And Cognition

## Seven-Stage Action Analysis

Use this model to diagnose where interaction breaks down:

1. Goal: what the person wants to achieve.
2. Intention: the chosen approach.
3. Action specification: which specific actions seem necessary.
4. Execution: carrying out the actions.
5. Perception: noticing the system state.
6. Interpretation: understanding what the state means.
7. Evaluation: comparing outcome with the goal.

Failures before execution are usually discoverability, planning, mapping, permission, vocabulary, or confidence problems. Failures after execution are often feedback, visibility, latency, ambiguous state, or conceptual model problems.

## Gulfs Of Execution And Evaluation

The gulf of execution is the gap between a user's goal and the actions the system makes available. The gulf of evaluation is the gap between the system's state and the user's ability to understand whether the goal was met.

Reduce the gulf of execution with:

- Clear primary action.
- Familiar vocabulary.
- Visible controls and direct manipulation.
- Good defaults and progressive disclosure.
- Constraints that guide valid action.

Reduce the gulf of evaluation with:

- In-place state changes.
- Clear result summaries.
- Status, progress, and timestamps.
- Previews and before/after comparisons.
- Explanations for failures and partial outcomes.

## Memory And Cognitive Load

People are good at recognition, pattern matching, and using environmental cues. They are weaker at exact recall, arbitrary sequences, and simultaneous tracking under stress.

Design tactics:

- Prefer recognition over recall.
- Keep labels close to controls.
- Show examples next to inputs.
- Preserve context across steps.
- Use sensible defaults and recent choices.
- Break long tasks into meaningful chunks.
- Avoid modes that require users to remember the current hidden state.

## Attention And Interruption

Most real work is interrupted. Design flows so users can safely pause, resume, and recover context.

Include:

- Draft saving.
- Clear current step and progress.
- Idempotent actions where possible.
- Back navigation without data loss.
- Summaries before irreversible submission.
- Notifications that distinguish urgent from informational.

## Emotion And Trust

Emotion changes how people think and act. Stress narrows attention and reduces exploration. Delight cannot compensate for uncertainty in high-stakes tasks.

Trust grows when the system is predictable, honest, recoverable, and legible. Avoid overclaiming automation, hiding uncertainty, or presenting destructive actions casually.

## Storytelling And Blame

People create explanations for unexpected outcomes, often blaming themselves or inventing causes from incomplete evidence. Use product behavior to make the true cause visible.

Good failure communication:

- Names the state, not the user's character.
- Explains what happened in task language.
- Shows what can be done next.
- Preserves user work where possible.
- Records enough context for support or incident review.
