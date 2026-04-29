---
name: typst
description: Use when helping users write, debug, format, or structure Typst documents, templates, packages, and snippets, especially layout, alignment, boxes, blocks, pages, tables, figures, headings, citations, math, styling with set/show rules, context, measurements, and Typst scripting.
---

# Typst

Use this skill for authoring Typst documents and reusable Typst code. Prefer idiomatic Typst markup, set rules, show rules, and small functions over compiler-level explanations unless the user asks about Typst internals.

## First Reads

- For day-to-day Typst authoring, read `references/user-authoring.md`.
- For layout, alignment, sizing, boxes, blocks, pages, tables, and measurements, read `references/user-layout.md`.
- For compiler or standard-library code changes in this repository, read `references/layout-internals.md` and `references/api-and-tests.md` only after confirming the task is about Typst implementation.

## Workflow

1. Identify whether the user wants a complete document, a template/function, a fix to existing Typst code, or an explanation.
2. Use public Typst syntax and functions first. Avoid referring to Rust internals unless relevant.
3. For formatting/layout questions, reason from the actual Typst layout model: inline vs block content, paragraph creation, relative sizing, alignment, and context.
4. Provide complete Typst snippets that can be pasted into a `.typ` file. Keep examples minimal but compilable.
5. When changing an existing document, preserve the user's structure and style unless it is the source of the bug.

## Core Mental Model

- Typst has markup, math, and code modes. In markup, `#` enters code; content blocks use `[...]`; code blocks use `{...}`.
- Set rules configure element properties in scope. Show rules transform selected content or apply set rules to selected elements.
- Inline content becomes paragraphs automatically; block-level content interrupts paragraphs. Use `box` to put block-like content inline and `block` to keep inline content out of a paragraph.
- `align` is block-level. For same-line separation, use `h(1fr)` instead of `align`.
- `start` and `end` follow text direction; `left` and `right` are physical.
- Relative sizes like `50%` resolve against a containing size; `fr` consumes remaining space in supported contexts such as grids, stacks, and horizontal spacing.
- `context` is required when code depends on style values, counters, locations, queries, or measurements that vary by placement.

## Output Style

- Prefer small, named helper functions for reusable styles.
- Use `#set` for global or scoped styling; use `#show` when transforming an element or applying style to only selected elements.
- Explain layout fixes in terms of Typst concepts, not CSS analogies, unless the user asks for a comparison.
- Include imports only when needed. If a package is needed, use the package's documented `#import` form and isolate it at the top.
