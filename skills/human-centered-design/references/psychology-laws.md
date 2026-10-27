# Psychology Laws

Use these heuristics to reason about interaction cost, perception, memory, decision-making, and stakeholder rationale. They are guides, not immutable laws; validate in context.

## Familiarity And Transfer

People bring expectations from other products and the wider world. When a pattern is common and good enough, copying it reduces learning cost. Depart from familiar patterns only when the new behavior is clearly better and well signposted.

Design implications:

- Use conventional placement for search, navigation, closing, back, save, and destructive actions.
- Match platform conventions for input, gestures, keyboard behavior, and accessibility.
- Do not use familiar-looking controls for surprising behavior.

## Target Size And Distance

Actions are easier when targets are large, near the pointer/finger path, and visually distinct.

Use for:

- Primary buttons.
- Touch targets.
- Frequently repeated controls.
- Time-sensitive actions.
- Drag handles and resize affordances.

Avoid tiny targets for destructive correction paths such as undo, remove, or close.

## Choice Complexity

More choices and less distinct choices slow decisions. Complexity is acceptable when users need power, comparison, or precision; it is harmful when users are trying to move through a routine path.

Reduce choice cost with:

- Strong defaults.
- Grouping and headings.
- Search and filtering.
- Progressive disclosure.
- Recommendations with transparent criteria.
- Clear distinction between common and advanced options.

## Working Memory

People can hold only a limited amount of arbitrary information while acting. Design should not require users to remember codes, formats, hidden settings, previous screens, or exact wording.

Support memory with:

- Recognition over recall.
- Persistent summaries.
- Inline examples.
- Side-by-side comparison.
- Recently used values.
- Copyable identifiers and deep links.

## Tolerance In Input

Be conservative in what the system does, but flexible in what it accepts. Human-entered data often has spaces, punctuation, mixed case, alternate date formats, and copy/paste artifacts.

Normalize where safe. Reject only when ambiguity would create real risk, and explain the repair.

## Peak-End Experience

People often remember the most intense point and the ending more than the average moment. In workflows, the stressful error, payment moment, approval wait, or final confirmation can dominate memory.

Design:

- Reduce anxiety at irreversible or costly moments.
- Make final status explicit and useful.
- Provide receipts, next steps, and recovery.
- Do not end with uncertainty after a successful action.

## Aesthetic-Usability Effect

People tend to perceive visually coherent designs as easier to use. This can help trust and confidence, but it can also mask usability problems.

Use visual polish to support:

- Hierarchy.
- Legibility.
- State.
- Consistency.
- Emotional tone appropriate to the task.

Do not let beauty hide missing feedback, ambiguous actions, poor accessibility, or unsafe defaults.

## Distinctiveness

Important items are easier to notice when they stand apart from surrounding items. Use contrast intentionally for the next action, selected state, warnings, and exceptions.

Avoid making everything high contrast. If everything shouts, nothing guides.

## Complexity Conservation

Some complexity cannot be removed; it can only be moved. Moving complexity from the interface into implementation is often good. Moving it into user memory, support teams, or documentation is usually bad unless the user gains meaningful power.

When simplifying, ask where the complexity went.

## Responsiveness

Fast, visible response keeps people oriented. Delays without feedback create duplicate actions, abandonment, and distrust.

Use immediate acknowledgement, optimistic UI only when rollback is safe, progress for long operations, and clear handling for retry, timeout, and partial success.
