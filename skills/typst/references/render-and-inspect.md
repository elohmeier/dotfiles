# Render and Inspect

Visual + structural inspection loop for Typst documents. Use after non-trivial layout, table, figure, or page-master changes — text-only reasoning misses real overflow, alignment, and pagination bugs.

## Render a single page as PNG

`typst compile` emits PNG with the `--pages` selector. For multi-page docs the output path needs a `{p}` template:

```sh
# Single page, fast preview
typst compile --pages 3 --ppi 96 doc.typ page-{p}.png

# Range, higher fidelity
typst compile --pages 2-4 --ppi 200 doc.typ page-{0p}.png

# All pages
typst compile --ppi 144 doc.typ page-{0p}-of-{t}.png
```

PPI guide:

- `96` — quick layout sanity check, small files, fast
- `144` (default) — readable text inspection
- `200`–`300` — typography review, kerning, hairlines

The Read tool reads PNGs as images, so the loop is: render → Read the PNG → diagnose → edit → re-render. Prefer the lowest PPI that shows the bug.

## Inspect structure with `typst query`

`query` runs the document through layout and returns serialized elements. Cheap, no rendering.

```sh
# All headings as JSON
typst query doc.typ heading --pretty

# A specific labelled element
typst query doc.typ "<fig:results>" --one --pretty

# Pull just one field across matches
typst query doc.typ figure --field caption

# Read a metadata value
typst query doc.typ "<config>" --one --field value
```

Selectors accept element functions (`heading`, `figure`, `table`, `math.equation`), labels (`<label>`), and `.where(...)` refinements written inside the doc and exposed via `metadata`.

## Extract page numbers / locations

`query` returns element fields but not `location()` directly. Inject `metadata` inside a `#context` block to capture page numbers, positions, or measurements:

```typ
#context {
  for h in query(heading) {
    [#metadata((title: h.body.text, page: h.location().page())) <toc>]
  }
}
```

Then:

```sh
typst query doc.typ "<toc>" --field value
# [{"title":"Intro","page":1},{"title":"Results","page":4}, ...]
```

Same pattern works for figures, tables, equations, and any custom element.

## Measure pass (programmatic layout debug)

Use `measure()` inside `#context` to print actual widths/heights without eyeballing the PNG:

```typ
#context {
  let m = measure(rect(width: 1fr, height: 2cm))
  [#metadata((w: m.width, h: m.height)) <m:rect>]
}
```

```sh
typst query doc.typ "<m:rect>" --one --field value
```

Useful for diagnosing `1fr` resolution, container overflow, or unexpected zero-size boxes.

## Watch mode

```sh
typst watch doc.typ out.pdf            # PDF, one file
typst watch doc.typ page-{0p}.png      # PNG per page, recompiles on save
```

Run in background (`run_in_background: true` in Bash) for tight feedback on long docs. Re-read the same PNG path after each save.

## When to render vs. query vs. read source

| Symptom                                            | Tool                                |
| -------------------------------------------------- | ----------------------------------- |
| Overflow, clipping, misalignment, wrong page break | render PNG                          |
| Wrong section/figure numbering, missing TOC entry  | `query` headings/figures            |
| "Where did this end up?" (page, position)          | `metadata` + `location()` + `query` |
| Unexpected `1fr` / `auto` size                     | `measure()` in `#context`           |
| Compile error, missing import                      | read source, no render needed       |

## Tips

- Always pass `--pages` when only inspecting one page — full-doc render wastes time on long docs.
- `{0p}` zero-pads filenames so a sorted directory listing matches reading order.
- `typst query --format yaml` is easier to skim than JSON for large result sets.
- For HTML docs, pass `--target html` to `query`; structure differs from paged.
- Re-render before reporting layout work done. PNG inspection is the Typst analogue of the `verify` skill's "run the app" rule.
