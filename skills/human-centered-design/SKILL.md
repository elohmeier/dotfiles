---
name: human-centered-design
description: Use when evaluating, designing, or improving products, services, interfaces, workflows, physical controls, documentation, onboarding, or AI experiences through human-centered design. Covers discoverability, affordances, signifiers, mappings, feedback, conceptual models, constraints, user errors, design thinking, usability reviews, research framing, accessibility, and ethical tradeoffs.
---

# Human-Centered Design

Use this skill when the task requires designing for how people perceive, decide, act, recover from mistakes, and build mental models. It applies to software, hardware, services, AI products, operational tools, forms, settings, onboarding, alerts, and physical-world interactions.

This skill is informed by summarized concepts from design, usability, psychology, information design, prototyping, and interface craft references. Do not quote or reproduce source text; apply the principles.

## First Move

1. Identify the user's actual goal, not only the visible request or proposed solution.
2. Name the human action cycle: goal, plan, action, system response, interpretation, next decision.
3. Look for missing discoverability, weak signifiers, confusing mapping, delayed feedback, avoidable memory load, and unsafe error paths.
4. Propose concrete design changes that shift burden from the person to the system.
5. Validate with realistic users, representative tasks, and observable behavior whenever possible.

## Reference Map

Load only the reference needed for the current task:

- `references/core-concepts.md`: affordances, signifiers, mapping, feedback, conceptual models, constraints, knowledge in the world vs head.
- `references/action-and-cognition.md`: gulfs of execution/evaluation, seven-stage action analysis, memory, emotion, attention, cognitive load.
- `references/error-and-safety.md`: slips, mistakes, forcing functions, confirmations, undo, resilience, automation risks, incident review.
- `references/research-and-design-process.md`: problem framing, double diamond, HCD loop, research methods, prototyping, usability testing.
- `references/review-checklists.md`: compact heuristics for UI, workflow, forms, dashboards, physical controls, AI interactions, and accessibility.
- `references/business-and-ethics.md`: feature creep, launch pressure, standardization, innovation, privacy, inclusion, moral obligations.
- `references/web-usability.md`: scanning behavior, navigation, wording, mobile, accessibility, and lightweight usability testing.
- `references/psychology-laws.md`: practical psychology heuristics for interaction design and stakeholder rationale.
- `references/ideation-and-sketching.md`: sketching, storyboards, state diagrams, Wizard-of-Oz prototypes, and design critiques.
- `references/interface-craft.md`: hierarchy, spacing, typography, color, controls, empty states, and visual polish.
- `references/information-design.md`: dense information displays, dashboards, small multiples, layering, color, and time/space narratives.
- `references/motivation-and-persuasive-design.md`: motivation, delight, progress, defaults, attention, and ethical persuasion boundaries.

## Working Style

- Prefer observed user behavior over stakeholder assumptions.
- Treat repeated "user error" as a design signal.
- Make system state, available actions, results, and recovery paths visible.
- Reduce memory demands through labels, defaults, examples, previews, history, and context.
- Use constraints to prevent invalid action before relying on warnings.
- Design for interruption, partial knowledge, fatigue, stress, assistive technology, and cultural variation.
- When tradeoffs are unavoidable, state who pays the cost and how risk is mitigated.

## Output Patterns

For design critique:

- Start with the user's likely goal and context.
- List the highest-risk usability failures first.
- For each issue, include principle, user impact, and concrete fix.
- Separate quick improvements from deeper product questions.
- Use `references/review-checklists.md`, then load a specialized reference if the surface is web, data-heavy, visual-interface-heavy, or automation-heavy.

For new design:

- Define user groups, jobs, constraints, and success criteria.
- Sketch the action path and feedback after each step.
- Specify states: empty, loading, partial, success, error, recovery, disabled, permission-limited.
- Include validation plan and failure modes.

For product or UX strategy:

- Reframe from feature request to user problem.
- Identify operational, technical, business, legal, and ethical constraints.
- Compare alternatives by user effort, risk, learnability, resilience, and long-term maintainability.
