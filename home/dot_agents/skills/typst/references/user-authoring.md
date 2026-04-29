# Typst User Authoring

Use this reference for writing or debugging `.typ` documents, snippets, templates, and packages.

## Modes And Syntax

Typst has three modes:

- Markup mode is the default for documents.
- Code mode is entered with `#` in markup or directly inside `{...}`.
- Math mode is entered with `$...$`; block math has spaces after the opening `$` and before the closing `$`.

Common forms:

```typst
= Heading
Text with #emph[emphasis], *strong*, _emphasis_, and $x^2$.

#let name = "Ada"
Hello, #name.

#let callout(title, body) = block(
  inset: 8pt,
  radius: 3pt,
  fill: luma(245),
)[
  *#title* \
  #body
]
```

In markup, a code expression started with `#` ends when Typst can no longer parse more of the expression. Use `#(...)` for binary expressions or complex inline code.

## Styling

Use set rules for normal styling:

```typst
#set page(margin: 2.5cm)
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.1")
```

Set rules are scoped. A top-level set rule applies until the end of the file; a set rule inside a content or code block applies only inside that block.

Use show-set rules to style selected elements:

```typst
#show heading.where(level: 1): set text(size: 18pt, weight: "bold")
#show link: set text(fill: blue)
```

Use transformational show rules to rewrite an element:

```typst
#show heading.where(level: 1): it => block(above: 1.2em, below: 0.6em)[
  #set align(center)
  #text(size: 18pt, weight: "bold", it.body)
]
```

Good practice: Prefer composable show-set rules where possible. Put non-overridable set rules inside transformational show rules only when the transformation requires them.

## Functions And Templates

A reusable Typst template is usually a function that accepts `body`:

```typst
#let project-template(title: none, author: none, body) = {
  set page(margin: 2.5cm)
  set text(font: "New Computer Modern", size: 11pt)
  set heading(numbering: "1.")

  if title != none {
    align(center, text(size: 18pt, weight: "bold", title))
    v(0.5em)
  }

  if author != none {
    align(center, emph(author))
    v(1em)
  }

  body
}

#show: project-template.with(
  title: [Report],
  author: [Ada Lovelace],
)
```

Use trailing content blocks for ergonomic APIs:

```typst
#let theorem(name, body) = block(inset: 8pt, stroke: 0.6pt + gray)[
  *#name.* #body
]

#theorem[Claim][Every finite tree has a leaf.]
```

## Context

Use `context` when code needs style values or location-dependent values.

Examples that require context:

```typst
#context text.size
#context counter(heading).get()
#context locate(<target>).position()
#context measure([Some content]).width
```

Keep dependent work inside the context expression because the result is contextual content, not a normal value that can be inspected outside its placement.

## Common Structures

Headings:

```typst
#set heading(numbering: "1.1")
= Introduction
== Background
```

Figures:

```typst
#figure(
  image("plot.png", width: 80%),
  caption: [Experiment results],
) <fig:results>

See @fig:results.
```

Bibliography:

```typst
This was shown by @knuth1984.

#bibliography("refs.bib")
```

Tables:

```typst
#table(
  columns: (auto, 1fr, auto),
  inset: 6pt,
  align: (left, left, right),
  [Name], [Description], [Score],
  [A], [Long text wraps here], [10],
)
```

Math:

```typst
Inline: $a^2 + b^2 = c^2$.

$
  sum_(i=1)^n i = (n(n + 1)) / 2
$
```

## Debugging User Code

- If text styling does not apply, check whether the content is inside a scope that overrides it.
- If paragraph styling does not apply, check whether the text became a semantic paragraph.
- If a value says context is required, wrap the smallest expression that needs it in `context`.
- If a function receives content, use content blocks `[...]`, not strings, when markup should remain markup.
- If alignment looks wrong in RTL documents, prefer `start`/`end` for logical alignment and `left`/`right` for physical alignment.
- If page content does not fit, check fixed heights, unbreakable blocks, large figures, and floats before changing page margins.
