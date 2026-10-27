# Core Concepts

## Human-Centered Design

Design starts from people: their goals, abilities, environments, tools, constraints, cultures, emotions, and failure modes. The product is responsible for making correct action understandable and recovery possible. Do not assume training, perfect attention, or careful reading.

## Discoverability

People should be able to tell what actions are possible and how to start. Hidden actions are acceptable only when they are secondary, consistently learnable, and backed by visible alternatives.

Ask:

- What can the user do here?
- Which action is primary, secondary, dangerous, or unavailable?
- Does the interface reveal the next useful step without instruction text?
- Can a new user begin safely?

## Affordances And Signifiers

An affordance is what an object or control permits. A signifier is the perceptible cue that communicates where and how to act. In digital interfaces, signifiers usually matter more than theoretical affordances because the screen can technically respond anywhere.

Use signifiers through:

- Shape, label, icon, position, cursor, focus style, grouping, motion, and state.
- Clear handles, affordance-revealing control geometry, and familiar patterns.
- Explicit labels for ambiguous icons or domain-specific actions.

Avoid:

- Clickable items that look like static text.
- Controls whose appearance suggests the wrong action.
- Icon-only destructive or rare actions without tooltip, label, or confirmation.

## Mapping

Mapping is the relationship between controls and outcomes. Good mapping makes cause and effect predictable. Natural mapping uses spatial, temporal, semantic, or cultural relationships that people already understand.

Examples:

- A stove control layout mirrors burner positions.
- A dashboard filter visually scopes only the panels it affects.
- A keyboard shortcut uses a memorable semantic relationship.
- A slider changes a value in the same direction the user expects.

When mapping is weak, add labels, grouping, previews, animation, or direct manipulation.

## Feedback

Feedback tells the user that an action was received, what changed, whether the result is acceptable, and what can happen next. Feedback must be timely and proportionate.

Design feedback for:

- Immediate acknowledgement: click, focus, pressed, pending, saving.
- Progress: loading, queued, retrying, blocked, estimated duration when useful.
- Result: success, partial success, validation failure, conflict, no-op.
- Recovery: undo, retry, edit, cancel, details, contact path.

Do not use success toasts as the only confirmation for important persistent changes; reflect the new state in place.

## Conceptual Models

A conceptual model is the user's explanation of how the system works. Users form one whether the design intends it or not. The interface, documentation, labels, defaults, and error messages together create the system image from which users infer the model.

Good conceptual models are:

- Coherent across screens and channels.
- Simple enough to predict common outcomes.
- Honest about limitations, latency, permissions, and automation.
- Reinforced by consistent language and state transitions.

## Constraints

Constraints reduce possible actions and guide correct behavior.

- Physical constraints: shape, size, position, reach, sequence, compatibility.
- Cultural constraints: conventions, symbols, norms, domain expectations.
- Semantic constraints: meaning of the situation limits plausible action.
- Logical constraints: relationships imply the only reasonable option.

Prefer constraints that prevent invalid action over messages that explain failure afterward. Use disabled states only when the reason and path to enablement are clear.

## Knowledge In The World Vs In The Head

Knowledge in the world is visible or available at the point of action: labels, examples, previews, constraints, history, defaults, and environment cues. Knowledge in the head is memory, skill, training, and experience.

Move knowledge into the world when:

- Tasks are infrequent.
- Stakes are high.
- Steps are arbitrary.
- Users are interrupted.
- Multiple roles or devices are involved.

Keep knowledge in the head only when the pattern is frequent, stable, highly practiced, and worth learning.
