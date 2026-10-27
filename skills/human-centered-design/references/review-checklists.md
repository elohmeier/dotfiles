# Review Checklists

Use these as prompts, not as a substitute for observing users.

## Universal Interaction Review

- Is the user's goal clear in this context?
- Is the primary next action visible?
- Are secondary actions available without competing with the primary path?
- Are labels written in the user's vocabulary?
- Is system status visible after every action?
- Can users predict what will happen before committing?
- Are destructive, expensive, or public actions differentiated?
- Can users undo, cancel, retry, or recover?
- Does the design preserve entered work across errors and navigation?
- Are empty, loading, error, partial, success, and permission states designed?
- Does the design work under interruption and low attention?
- Does the design support scanning before reading?
- Are common actions reachable with low motor precision and low cognitive effort?

## Forms

- Ask only for information needed now.
- Group fields by user meaning, not database schema.
- Put help text and examples where decisions happen.
- Validate early where useful, but avoid noisy interruption.
- Explain format requirements before failure.
- Preserve data after errors.
- Mark optional fields explicitly when most fields are required.
- Use input types, masks, and defaults to reduce typing.
- Summarize before high-stakes submission.
- Allow paste into fields where users reasonably store generated values, especially passwords and codes.
- Accept common human formats and normalize internally instead of forcing database formats.
- If validation fails, identify the field, the problem, and the repair.

## Navigation And Workflow

- The current location and task state are visible.
- Back and cancel behavior match user expectations.
- Long flows can be paused and resumed.
- Cross-step dependencies are explained.
- Users can review accumulated choices.
- The workflow does not require hidden knowledge from another channel.
- Branching logic does not strand users.
- Navigation labels match what users are seeking, not internal team names.
- Breadcrumbs, section headings, and selected states agree with each other.

## Dashboards And Operational Tools

- The dashboard answers a specific operational question.
- Critical status is visible without interpreting decorative visuals.
- Time ranges, filters, freshness, and data gaps are obvious.
- Drilldowns preserve context.
- Alerts distinguish urgency, owner, impact, and next action.
- Tables support scanning, comparison, sorting, and copying.
- Dangerous bulk actions have preview and rollback where possible.
- Related views use consistent encodings so users can compare without relearning.
- Dense displays use grouping, layering, and annotation instead of decorative separation.

## Physical Controls

- Controls are visible and reachable in real use conditions.
- Control layout maps to the controlled parts.
- Shape and movement suggest correct operation.
- Feedback is perceptible through sight, sound, touch, or position.
- Similar controls with different consequences are differentiated.
- Safety-critical states are visible at a distance when needed.
- The design accounts for gloves, lighting, fatigue, noise, and posture.

## AI And Automation

- The user knows when automation is acting.
- The system communicates confidence, uncertainty, and limits.
- Users can inspect evidence or reasoning when stakes require it.
- Outputs are editable and reversible.
- Automation does not invent authority it does not have.
- Failure modes include escalation, fallback, and audit trail.
- The design avoids nudging users into overtrust.

## Accessibility And Inclusion

- Keyboard-only operation is complete and visible.
- Focus order matches visual and task order.
- Text alternatives exist for meaningful images and icons.
- Color is not the only carrier of meaning.
- Contrast supports low-vision use.
- Motion is avoidable when it can distract or harm.
- Copy avoids idioms, unnecessary jargon, and culturally narrow assumptions.
- Error messages are announced and linked to fields for assistive technology.
- Touch targets and spacing support motor variation.

## Visual Interface Craft

- Visual hierarchy matches task importance, not DOM order or implementation order.
- Spacing communicates grouping unambiguously.
- Text line length, size, and contrast support sustained reading.
- Interactive elements look interactive in their normal state.
- Icons have labels when recognition is not near-universal.
- Color palettes include semantic roles, neutral roles, focus, hover, disabled, and error states.
- Empty states explain what belongs there and offer a next action when one exists.
- User-generated content cannot break layout, contrast, or readability.
