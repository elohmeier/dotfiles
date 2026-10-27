# Source navigation

Use this reference to locate authoritative definitions quickly and to keep version evidence reproducible.

## Contents

- [Resolve and fingerprint the clones](#resolve-and-fingerprint-the-clones)
- [Apply source precedence](#apply-source-precedence)
- [Navigate ECS](#navigate-ecs)
- [Navigate OpenTelemetry](#navigate-opentelemetry)
- [Search efficiently](#search-efficiently)
- [Compare versions without changing worktrees](#compare-versions-without-changing-worktrees)

## Resolve and fingerprint the clones

Use `ECS_REPO_PATH` and `OTEL_SEMCONV_REPO_PATH` when set. Otherwise use:

```sh
ECS_REPO_PATH=/Users/enno/repos/github.com/elastic/ecs
OTEL_SEMCONV_REPO_PATH=/Users/enno/repos/github.com/open-telemetry/semantic-conventions
```

Verify the paths and record the exact state:

```sh
git -C "$ECS_REPO_PATH" status --short --branch
git -C "$ECS_REPO_PATH" describe --tags --always --dirty
sed -n '1p' "$ECS_REPO_PATH/version"
sed -n '1p' "$ECS_REPO_PATH/otel-semconv-version"
git -C "$OTEL_SEMCONV_REPO_PATH" status --short --branch
git -C "$OTEL_SEMCONV_REPO_PATH" describe --tags --always --dirty
sed -n '1,20p' "$OTEL_SEMCONV_REPO_PATH/model/manifest.yaml"
```

Treat a dirty marker as part of the evidence. Do not discard or overwrite local changes.

## Apply source precedence

1. Use the ref required by the user's dependency or deployment contract.
2. Use canonical model files for exact machine-readable definitions.
3. Use generated documentation for assembled context and efficient reading.
4. Use general/manual prose for cross-cutting rules that are not encoded in a group.
5. Use changelogs and Git history to explain migrations, not to override the target ref.

For OTel, distinguish vocabulary from use: a registry attribute may be stable while a group that uses it is development, or its requirement level may vary by signal and role. Inspect both.

For ECS-to-OTel alignment, use the SemConv version named by ECS `otel-semconv-version`. The current OTel working tree may represent a different contract.

## Navigate ECS

- `version`: ECS model version for the checkout.
- `otel-semconv-version`: SemConv tag used to validate and generate ECS alignment data.
- `schemas/*.yml`: canonical fieldsets, field types, descriptions, levels, examples, allowed values, normalization, reuse, and `otel:` relations.
- `schemas/README.md`: schema syntax and reuse semantics.
- `generated/ecs/ecs_flat.yml`: expanded dotted-name lookup and computed consumer representation.
- `generated/ecs/ecs_nested.yml`: expanded nested consumer representation.
- `docs/reference/ecs-principles-implementation.md`: event construction, timestamps, origin, and field-use patterns.
- `docs/reference/ecs-guidelines.md`, `ecs-conventions.md`, and `ecs-custom-fields-in-ecs.md`: naming, types, and extension guidance.
- `docs/reference/ecs-using-categorization-fields.md` and related allowed-value pages: `event.kind`, `category`, `type`, and `outcome` usage.
- `docs/reference/ecs-opentelemetry.md`: meanings of ECS mapping relation types.
- `docs/reference/ecs-otel-alignment-{overview,details}.md`: generated readable mapping indexes.
- `scripts/docs/otel-integration.md`: mapping validation and generation details.

Locate a dotted ECS field in the flat artifact, then inspect its owner under `schemas/`:

```sh
rg -n -F -C 8 'http.request.method' "$ECS_REPO_PATH/generated/ecs/ecs_flat.yml"
rg -n -F -C 12 'name: request.method' "$ECS_REPO_PATH/schemas"
```

Do not edit generated field or alignment documentation.

## Navigate OpenTelemetry

- `model/manifest.yaml`: schema URL and model-level version information.
- `model/version.properties`: semantic model syntax version, not the SemConv release tag.
- `model/<domain>/registry.{yaml,yml}`: attribute definitions, types, stability, examples, and deprecations.
- `model/<domain>/{common,spans,metrics,events,logs,entities}.{yaml,yml}`: convention groups and contextual use.
- `model/**/deprecated/` and `*-deprecated.*`: legacy definitions and replacements.
- `docs/<domain>/`: generated, assembled conventions plus hand-written normative sections.
- `docs/registry/attributes/<domain>.md`: generated attribute registry for quick reading.
- `docs/general/naming.md`: attribute, span, metric, and event naming rules.
- `docs/general/{attribute,signal}-requirement-level.md`: inclusion behavior.
- `docs/general/recording-errors.md`: consistent error behavior across logs, spans, and metrics.
- `docs/configuration/version-selection.md`: stable, experimental, and dual-emit selection.

Search an attribute definition and all contextual references:

```sh
rg -n -F -C 8 'http.request.method' "$OTEL_SEMCONV_REPO_PATH/model/http"
rg -n -F -C 6 'http.request.method' "$OTEL_SEMCONV_REPO_PATH/docs/http" "$OTEL_SEMCONV_REPO_PATH/docs/registry/attributes/http.md"
```

Search a metric by exact name and inspect its whole group for instrument, unit, stability, and dimensions:

```sh
rg -n -F -C 16 'http.server.request.duration' "$OTEL_SEMCONV_REPO_PATH/model"
```

## Search efficiently

Run the bundled search from the skill directory:

```sh
scripts/semconv-search.sh --both 'http.request.method'
scripts/semconv-search.sh --otel 'http.server.request.duration'
scripts/semconv-search.sh --ecs-aligned 'http.request.method'
scripts/semconv-search.sh --otel --readable 'http.server.request.duration'
scripts/semconv-search.sh --both --all-sources 'trace.id'
scripts/semconv-search.sh --regex '^(.*\.)?error\.type$'
```

Start with an exact dotted name using fixed-string mode. The default scope searches canonical model/schema files plus the expanded ECS field locator. Add `--readable` for generated documentation only or `--all-sources` for both scopes. Search by domain plus concept only when no exact standard name is known. Exclude broad web searches until the local clones and relevant refs have been exhausted.

Use `rg --files` to discover a domain's likely files before searching the entire repository:

```sh
rg --files "$OTEL_SEMCONV_REPO_PATH/model" | rg '/(http|network|server)/'
rg --files "$ECS_REPO_PATH/schemas" | rg '/(http|network|server)\.yml$'
```

## Compare versions without changing worktrees

Read ECS's aligned SemConv at its pinned tag:

```sh
OTEL_ALIGNED_REF=$(sed -n '1p' "$ECS_REPO_PATH/otel-semconv-version")
git -C "$OTEL_SEMCONV_REPO_PATH" grep -n -F -e 'http.request.method' "$OTEL_ALIGNED_REF" -- model docs
git -C "$OTEL_SEMCONV_REPO_PATH" show "$OTEL_ALIGNED_REF:model/http/registry.yaml"
```

Inspect a released ECS definition without checkout:

```sh
git -C "$ECS_REPO_PATH" grep -n -F -e 'name: request.method' v9.4.0 -- schemas
git -C "$ECS_REPO_PATH" show v9.4.0:schemas/http.yml
```

Use `git log -S`, `git log -G`, and `git blame` only after identifying the exact source file. Report history as rationale; keep the selected version's file as the contract.
