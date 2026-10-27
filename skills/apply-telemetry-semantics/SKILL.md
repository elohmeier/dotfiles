---
name: apply-telemetry-semantics
description: Apply and review OpenTelemetry Semantic Conventions and Elastic Common Schema (ECS) semantics using authoritative local Git sources. Use for implementing or reviewing instrumentation, structured logging, OTLP transforms, collectors, ingest pipelines, schemas, dashboards, and tests involving logs, log-based events, metrics, spans/traces, resources/entities, trace correlation, ECS fields, OTel attributes, metric instruments, convention stability, requirement levels, or ECS-to-OTel mappings and conflicts.
---

# Apply Telemetry Semantics

Base decisions on the checked-out specifications, not memory or name similarity. Treat OpenTelemetry SemConv and ECS as related standards with explicit mappings, not as one interchangeable schema.

## Start from local sources

1. Resolve the repositories from `ECS_REPO_PATH` and `OTEL_SEMCONV_REPO_PATH`, or use these defaults:
   - `/Users/enno/repos/github.com/elastic/ecs`
   - `/Users/enno/repos/github.com/open-telemetry/semantic-conventions`
2. Record the target versions before choosing names or behavior. Read the project or dependency version when one is supplied; otherwise record `git describe --tags --always --dirty` for both clones, ECS `version`, OTel `model/manifest.yaml`, and ECS `otel-semconv-version`.
3. Do not pull, switch branches, or check out tags merely to answer a question. Use `git grep` and `git show` against the required ref.
4. Run `scripts/semconv-search.sh` for the first pass, then inspect the focused files it returns. Use `--ecs-aligned` when evaluating ECS's declared OTel mappings.
5. Read [references/source-navigation.md](references/source-navigation.md) before any non-trivial lookup, version comparison, or standards change.

## Follow the implementation workflow

### 1. Define the telemetry contract

Identify all of these before editing code:

- Signal: log record, log-based event, metric, span, resource/entity, or an OTLP envelope field.
- Domain and role: for example HTTP server, database client, messaging consumer, or process entity.
- Layer: producer instrumentation, SDK/export, collector transform, ECS ingest/storage, or consumer/query.
- Target versions: instrumentation library, SemConv, OTLP, ECS, and backend integration where relevant.
- Compatibility constraint: stable-only, experimental opt-in, dual emission, or migration from a deprecated convention.

Do not force one field into several layers that model different concepts.

### 2. Resolve OpenTelemetry semantics in context

Search both the attribute or metric definition and the signal-specific convention group.

- Use `model/<domain>/registry.*` for attribute identity, value type, examples, stability, and deprecation.
- Use `model/<domain>/{spans,metrics,events,logs,entities,common}.*` for applicability, role, signal stability, requirement level, span name/kind/status, metric instrument/unit, and contextual overrides.
- Use the corresponding `docs/<domain>/` page to read assembled generated tables and normative prose efficiently.
- Check `docs/general/` for naming, requirement levels, recording errors, and signal-wide rules.

Never infer that a registered attribute applies to a signal. A registry entry defines vocabulary; the convention group defines use. Prefer the most specific group when it overrides a shared requirement level.

### 3. Resolve ECS semantics and placement

- Use `schemas/*.yml` as the canonical editable ECS source.
- Use `generated/ecs/ecs_flat.yml` to locate an expanded dotted field and inspect computed reuse, type, normalization, allowed values, and `otel` mappings.
- Return to the owning `schemas/*.yml` file before proposing an ECS schema edit.
- Check the relevant usage or implementation guide for placement, categorization, timestamp, and custom-field guidance.
- Treat generated field reference and alignment pages as readable indexes; do not edit them directly.

For stored ECS events, verify required base fields and applicable `event.*`, `data_stream.*`, categorization, outcome, timing, and correlation fields instead of copying only similarly named OTel attributes.

### 4. Reconcile ECS and OTel explicitly

Read the ECS field's `otel:` relation before mapping it:

- `match`: use the same name only after confirming type, value rules, stability, and signal placement.
- `equivalent`: map or alias only when the representations are compatible.
- `related`: transform with an explained rule; do not alias.
- `conflict`: keep distinct representations or implement an explicit lossy conversion with tests.
- `metric`: use the OTel metric data model; do not turn the ECS metric-like field into an OTel attribute.
- `otlp`: map an intrinsic OTLP field such as trace context, not a semantic attribute.
- `na`: do not invent an OTel counterpart.

Compare mappings against the SemConv tag in ECS `otel-semconv-version`. Revalidate against a newer target SemConv separately when the implementation is newer than that pin.

### 5. Implement at the owning layer

- Preserve exact dotted names, value types, units, casing, enumerations, and conditional behavior.
- Put identity and environment data on the resource/entity when the convention says so; put operation data on the record or span.
- Follow Required and Conditionally Required behavior. Emit Recommended data by default unless the documented exceptions apply. Gate Opt-In data behind explicit configuration.
- Keep development conventions off by default in stable instrumentation unless the version-selection rules allow an explicit opt-in.
- Bound metric and span-name cardinality. Never add raw IDs, URLs, statements, user input, exception messages, or other unbounded values as metric dimensions without an explicit convention.
- Avoid duplicate exception or error recording across logs, spans, and metrics. Apply the cross-signal error rules from the target version.
- Use a project-specific namespace only after proving no applicable standard convention exists. Document the gap and migration plan.

Read [references/signal-checklists.md](references/signal-checklists.md) for the affected signal before implementing or reviewing code.

### 6. Verify behavior, not only constants

Test emitted telemetry or transformed payloads for:

- presence and absence under success, error, conditional, and opt-in cases;
- exact names, types, units, enum values, and resource-versus-record placement;
- span name, kind, status, events, and trace correlation;
- metric instrument kind and stable attribute sets across increments/decrements;
- ECS mappings, timestamp semantics, array normalization, and conflicts;
- cardinality, privacy, redaction, and backwards-compatible migration behavior.

Prefer SDK/exporter test readers, collector golden fixtures, or captured OTLP over tests that only assert constant definitions.

## Report evidence

State the target versions and distinguish verified requirements from recommendations or inferences. Cite the local source path and line for every non-obvious semantic decision. For mapping work, report the OTel item, signal/group, requirement level, stability, ECS field, relation, conversion rule, and any information loss.

Do not present `main` as a released contract, treat matching names as proof of equivalence, or silently combine current SemConv with ECS's older alignment pin.
