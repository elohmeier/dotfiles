---
name: paperless-utils
description: Paperless-NGX document management CLI. Use when the user needs to search, download, inspect, upload, or manage documents in Paperless-NGX. Triggers include requests to "find a document", "search paperless", "download from paperless", "get document details", "list tags", "list correspondents", "upload to paperless", "create a note", "analyze a receipt", or any task involving Paperless-NGX document management.
allowed-tools: Bash(paperless-utils:*), Bash(uv run paperless-utils:*)
---

# Paperless-NGX Document Management with paperless-utils

A Python CLI for searching, downloading, inspecting, and managing documents in Paperless-NGX.

## Setup

The CLI requires connection details via environment variables or flags:

```bash
export PAPERLESS_URL="https://paperless.example.com"
export PAPERLESS_TOKEN="your-api-token"
```

Or pass them as flags: `paperless-utils --url <URL> --token <TOKEN> <command>`.

Run from the project directory with `uv run paperless-utils` or install globally.

## Core Workflow

The typical workflow for finding and inspecting documents:

1. **Search**: Find documents by query, date, correspondent, tag, or type
2. **Inspect**: Get detailed info on a specific document by ID
3. **Download**: Download the document file(s)

```bash
# Search for invoices from Amazon
paperless-utils search -q "invoice" -c "Amazon"

# Get details on a specific document
paperless-utils get 123

# Download a document
paperless-utils download 123
```

## Searching Documents

The `search` command is the primary entry point. It supports extensive filtering and has subcommands for acting on results.

```bash
# Full-text search
paperless-utils search -q "invoice"

# Filter by correspondent (name or ID)
paperless-utils search -c "Amazon"

# Filter by tag
paperless-utils search -t "Important"

# Filter by document type
paperless-utils search -d "Invoice"

# Filter by date ranges
paperless-utils search --created-after 2024-01-01 --created-before 2024-12-31
paperless-utils search --added-after -5d
paperless-utils search -y 2024

# Filter by specific document IDs
paperless-utils search -i 123 -i 456

# Combine filters
paperless-utils search -q "receipt" -c "Amazon" -t "Tax" -y 2024

# Limit results
paperless-utils search -q "invoice" -l 5

# Change ordering (default: -added)
paperless-utils search --ordering "-created"

# JSON output
paperless-utils search -q "invoice" list --json
```

### Search Subcommands

After filtering, use subcommands to act on the results:

```bash
# Download matching documents
paperless-utils search -q "invoice" -c "Amazon" download --output-dir ./invoices

# Download to ZIP
paperless-utils search -t "Tax" -y 2024 download --zip tax-2024.zip

# Parse documents to extract custom field values (using LLM)
paperless-utils search -d "Invoice" parse --update

# Update document content using Marker PDF extraction
paperless-utils search -i 123 update-content

# Suggest titles using LLM
paperless-utils search -c "Amazon" suggest-titles
```

## Inspecting Documents

```bash
# Get full document details (metadata, content, tags, custom fields)
paperless-utils get 123

# JSON output
paperless-utils get 123 -o json

# Get document thumbnail (base64 to stdout, useful for vision)
paperless-utils thumbnail 123

# Save thumbnail to file
paperless-utils thumbnail 123 -o thumb.webp
```

## Downloading Documents

```bash
# Download a single document by ID
paperless-utils download 123

# Download to specific path
paperless-utils download 123 -o ./invoice.pdf

# Bulk download via search
paperless-utils search -c "Amazon" download --output-dir ./amazon-docs
paperless-utils search -t "Tax" download --zip tax-docs.zip --no-strip-metadata
```

## Uploading Documents

```bash
# Upload a single file
paperless-utils upload invoice.pdf

# Upload with metadata
paperless-utils upload invoice.pdf -c "Amazon" -d "Invoice" -t "Tax"

# Upload multiple files
paperless-utils upload *.pdf

# Set creation date
paperless-utils upload invoice.pdf --created-date 2024-01-15

# Dry run
paperless-utils upload invoice.pdf --dry-run
```

## Updating Documents

```bash
# Update title
paperless-utils update 123 --title "New Title"

# Update correspondent
paperless-utils update 123 -c "Amazon"

# Update document type
paperless-utils update 123 -d "Invoice"

# Replace all tags
paperless-utils update 123 -t "Invoice" -t "2024"

# Add/remove individual tags
paperless-utils update 123 --add-tag "Important"
paperless-utils update 123 --remove-tag "Inbox"

# Update custom fields
paperless-utils update 123 -f "VAT Total=19.99" -f "Gross Total=119.99"

# Update date
paperless-utils update 123 --date 2024-01-15

# Preview changes
paperless-utils update 123 --title "New Title" --dry-run
```

## Browsing Metadata

```bash
# List all correspondents
paperless-utils list-correspondents

# Search correspondents with fuzzy matching
paperless-utils list-correspondents --search "Hospital"

# List all tags
paperless-utils list-tags

# List all document types
paperless-utils list-document-types

# List custom fields
paperless-utils list-custom-fields

# Create new metadata entries
paperless-utils create-correspondent "Amazon"
paperless-utils create-tag "Important" --color "#ff0000"
paperless-utils create-document-type "Invoice"
```

## Creating Notes

Create Markdown notes, convert to PDF via Typst, and upload:

```bash
paperless-utils note --title "Meeting Notes" -c "Personal" -d "Note"
paperless-utils note --template phone-call --title "Call with Client"
paperless-utils note --template meeting
paperless-utils note --skip-upload -o note.pdf
```

## AI-Powered Analysis

### Azure Document Intelligence

```bash
# Analyze a receipt
paperless-utils analyze-document 123 --model-type prebuilt-receipt

# Analyze an invoice
paperless-utils analyze-document 456 --model-type prebuilt-invoice

# Update custom fields with extracted data
paperless-utils analyze-document 123 --update-custom-fields

# Update creation date from transaction date
paperless-utils analyze-document 123 --update-creation-date

# Update correspondent from merchant name
paperless-utils analyze-document 123 --update-correspondent

# JSON output
paperless-utils analyze-document 123 -o json
```

Requires `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY`.

## PDF Operations

```bash
# Remove password from a PDF document
paperless-utils remove-password 123
paperless-utils remove-password 123 --password secret123 --delete-original
```

## Common Patterns

### Find and download recent documents from a correspondent

```bash
paperless-utils search -c "Amazon" --added-after -7d download --output-dir ./recent
```

### Bulk update metadata for search results

```bash
# First review what you'll get
paperless-utils search -q "old name" list

# Then use the update command on individual docs
paperless-utils update 123 -c "New Correspondent"
```

### Extract data from receipts and update fields

```bash
paperless-utils search -d "Receipt" -c "Amazon" list
paperless-utils analyze-document 123 --update-custom-fields --update-creation-date --update-correspondent
```

### Inspect a document's full content for research

```bash
paperless-utils get 123          # See metadata + content
paperless-utils thumbnail 123    # Get visual thumbnail (base64)
```

## Environment Variables

| Variable                               | Description                                                                |
| -------------------------------------- | -------------------------------------------------------------------------- |
| `PAPERLESS_URL`                        | Paperless-NGX instance URL (required)                                      |
| `PAPERLESS_TOKEN`                      | API authentication token (required)                                        |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Azure DI endpoint (for analyze-document)                                   |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY`      | Azure DI API key (for analyze-document)                                    |
| `OLLAMA_URL`                           | Ollama API URL (for parse/suggest-titles, default: http://localhost:11434) |
| `EDITOR`                               | Editor for note creation (default: vim)                                    |
