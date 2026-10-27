---
name: opendataloader-pdf
description: PDF data extraction CLI. Use when the user needs to extract text, tables, or structured data from PDF files, convert PDFs to Markdown/JSON/HTML, parse scanned PDFs, or work with PDF accessibility. Triggers include "parse PDF", "extract from PDF", "convert PDF to markdown", "PDF to JSON", "OCR this PDF", "extract tables from PDF", or any task involving PDF content extraction.
allowed-tools: Bash(opendataloader-pdf *)
---

# PDF Extraction with opendataloader-pdf

## Usage

```bash
opendataloader-pdf [options] <INPUT FILE OR FOLDER>...
```

Input is positional (no `-i` flag). Multiple files and folders accepted. Folders are processed recursively.

## Quick Examples

```bash
# PDF to Markdown
opendataloader-pdf -f markdown -o output/ document.pdf

# PDF to JSON (with bounding boxes, default format)
opendataloader-pdf -o output/ document.pdf

# Multiple formats at once
opendataloader-pdf -f markdown,json -o output/ document.pdf

# Process entire folder
opendataloader-pdf -f markdown -o output/ ./pdfs/

# Specific pages only
opendataloader-pdf -f markdown --pages "1,3,5-7" -o output/ document.pdf

# Suppress logging
opendataloader-pdf -q -f markdown -o output/ document.pdf
```

## Output Formats (`-f` / `--format`)

Comma-separated. Default: `json`.

| Value                  | Description                                           |
| ---------------------- | ----------------------------------------------------- |
| `json`                 | Structured JSON with bounding boxes for every element |
| `markdown`             | Clean Markdown output                                 |
| `markdown-with-html`   | Markdown with HTML tags for complex formatting        |
| `markdown-with-images` | Markdown with extracted images referenced             |
| `text`                 | Plain text                                            |
| `html`                 | HTML representation                                   |
| `pdf`                  | Tagged PDF with structure tree                        |

## Common Options

| Option         | Short | Type    | Default   | Description                        |
| -------------- | ----- | ------- | --------- | ---------------------------------- |
| `--output-dir` | `-o`  | string  | input dir | Output directory                   |
| `--format`     | `-f`  | string  | json      | Output formats (comma-separated)   |
| `--pages`      |       | string  | all       | Pages to extract (e.g., `1,3,5-7`) |
| `--password`   | `-p`  | string  |           | Password for encrypted PDFs        |
| `--quiet`      | `-q`  | boolean | false     | Suppress console logging           |

## Table & Structure Options

| Option                   | Type    | Default | Description                                              |
| ------------------------ | ------- | ------- | -------------------------------------------------------- |
| `--table-method`         | string  | default | `default` (border-based) or `cluster` (border + cluster) |
| `--reading-order`        | string  | xycut   | `xycut` (XY-Cut++ layout-aware) or `off`                 |
| `--use-struct-tree`      | boolean | false   | Use PDF structure tree for tagged PDFs                   |
| `--detect-strikethrough` | boolean | false   | Wrap strikethrough text with `~~` (experimental)         |

## Text Processing Options

| Option                    | Type    | Default | Description                        |
| ------------------------- | ------- | ------- | ---------------------------------- |
| `--keep-line-breaks`      | boolean | false   | Preserve original line breaks      |
| `--replace-invalid-chars` | string  | space   | Replacement for invalid characters |
| `--include-header-footer` | boolean | false   | Include page headers/footers       |

## Image Options

| Option           | Type   | Default  | Description                                    |
| ---------------- | ------ | -------- | ---------------------------------------------- |
| `--image-output` | string | external | `off`, `embedded` (Base64), `external` (files) |
| `--image-format` | string | png      | `png` or `jpeg`                                |
| `--image-dir`    | string |          | Custom directory for extracted images          |

## Page Separator Options

| Option                      | Type   | Default | Description                                                               |
| --------------------------- | ------ | ------- | ------------------------------------------------------------------------- |
| `--markdown-page-separator` | string | none    | Separator between pages in Markdown. Use `%page-number%` for page numbers |
| `--text-page-separator`     | string | none    | Separator between pages in text output                                    |
| `--html-page-separator`     | string | none    | Separator between pages in HTML output                                    |

## Safety & Privacy

| Option                 | Type    | Default | Description                                                                    |
| ---------------------- | ------- | ------- | ------------------------------------------------------------------------------ |
| `--sanitize`           | boolean | false   | Mask emails, phones, IPs, credit cards, URLs                                   |
| `--content-safety-off` | string  |         | Disable safety filters: `all`, `hidden-text`, `off-page`, `tiny`, `hidden-ocg` |

## Hybrid Mode (AI Backend)

For scanned PDFs, OCR, complex tables, formulas, and image descriptions. Requires a running hybrid server.

| Option              | Type    | Default | Description                                              |
| ------------------- | ------- | ------- | -------------------------------------------------------- |
| `--hybrid`          | string  | off     | Backend: `off`, `docling-fast`                           |
| `--hybrid-mode`     | string  | auto    | `auto` (dynamic triage) or `full` (all pages to backend) |
| `--hybrid-url`      | string  |         | Backend server URL                                       |
| `--hybrid-timeout`  | string  | 30000   | Request timeout in ms                                    |
| `--hybrid-fallback` | boolean | false   | Fall back to Java on backend error                       |

## Common Patterns

### Extract tables from a PDF

```bash
opendataloader-pdf -f json --table-method cluster -o output/ tables.pdf
```

### Convert scanned PDF with OCR

```bash
opendataloader-pdf -f markdown --hybrid docling-fast --hybrid-mode full -o output/ scan.pdf
```

### Tagged PDF with structure tree

```bash
opendataloader-pdf -f markdown --use-struct-tree -o output/ tagged.pdf
```

### Markdown with page numbers

```bash
opendataloader-pdf -f markdown --markdown-page-separator "---\nPage %page-number%\n---" -o output/ doc.pdf
```

### Privacy-safe extraction

```bash
opendataloader-pdf -f markdown --sanitize -o output/ sensitive.pdf
```

### Extract with embedded images (Base64)

```bash
opendataloader-pdf -f markdown-with-images --image-output embedded -o output/ doc.pdf
```
