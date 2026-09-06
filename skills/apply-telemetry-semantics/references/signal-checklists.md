# Signal and interoperability checklists

Load the sections for the signals and layers in scope. Verify each item against the selected Git ref; do not treat this checklist as a field catalog.

## Contents

- [Shared checks](#shared-checks)
- [Logs and log-based events](#logs-and-log-based-events)
- [Spans and traces](#spans-and-traces)
- [Metrics](#metrics)
- [Resources and entities](#resources-and-entities)
- [ECS event storage](#ecs-event-storage)
- [ECS and OTel interoperability](#ecs-and-otel-interoperability)
- [Verification matrix](#verification-matrix)

## Shared checks

- Identify the domain, operation, client/server/producer/consumer role, and precise signal group.
- Distinguish OTLP envelope fields, OTel semantic attributes, resource attributes, log record fields, metric metadata, and ECS document fields.
- Confirm the convention group's stability independently of each attribute's stability.
- Confirm contextual requirement levels; do not copy the registry's vocabulary into every signal.
- Preserve value types, arrays, casing, well-known values, units, and conditional clauses exactly.
- Check deprecations and migration instructions at the target ref.
- Check cardinality, collection cost, privacy, credentials, personal data, and payload/body capture.
- Keep custom attributes in a project-owned namespace and avoid collisions with standard namespaces.
- Keep trace and span IDs in native context or OTLP fields. Let the exporter or ingest layer expose ECS `trace.id` and `span.id`; do not add duplicate OTel attributes merely for correlation unless the target convention explicitly requires them.

## Logs and log-based events

- Distinguish an ordinary log record from a named log-based event; apply event conventions only to the latter.
- Verify timestamp, observed timestamp where applicable, severity number/text, body, event name, attributes, resource, scope, and trace context at the correct layer.
- Keep the human-readable message or structured body separate from queryable semantic attributes.
- Put transmission metadata such as log file or stream data where the selected convention requires it; do not assume it describes the resource.
- Apply the domain-specific event or exception group, including its attribute requirements and stability.
- Avoid recording the same exception at multiple instrumentation layers. Preserve exception type, message, and stacktrace only where the selected exception convention and privacy policy allow them.
- When serializing as ECS, distinguish `message` from `log.original`; populate `@timestamp`, `ecs.version`, applicable `event.*` categorization, and native trace correlation fields.
- Test structured and unstructured bodies, missing severity, correlated and uncorrelated records, error paths, redaction, and multiline stack traces.

## Spans and traces

- Verify span creation boundary and whether an existing span should be enriched instead of creating a duplicate.
- Verify exact span name construction, low-cardinality placeholders, span kind, start/end timing, and parent/context propagation.
- Verify Required, Conditionally Required, Recommended, and Opt-In attributes for the precise role.
- Set span status according to domain-specific status rules; leave it unset for success when the convention requires that behavior.
- Apply `error.type` and exception recording consistently. Do not treat every protocol error or handled exception as a failed operation without checking the convention.
- Check events and links separately from attributes. Do not flatten them into attributes merely to fit ECS.
- Verify retry, redirect, messaging creation/processing, and asynchronous boundaries where applicable.
- Test success, classified error, cancellation/timeout, missing conditional inputs, propagation failure, and sampling-relevant data available at span start.

## Metrics

- Prefer an existing standard metric over a custom instrument.
- Verify exact metric name, signal requirement level, stability, description, instrument kind, value type annotation, and UCUM unit.
- Verify every allowed attribute on that metric group and its contextual requirement level; do not reuse all span attributes as dimensions.
- Keep dimensions bounded. Exclude trace/span IDs, full URLs, raw statements, exception messages, user identifiers, and other unbounded values unless explicitly standardized for that metric.
- Record duration using the specified unit, commonly seconds; do not encode units in the name unless the convention explicitly does so.
- Use matching attribute sets for paired UpDownCounter increments and decrements.
- Follow the selected convention's error aggregation: commonly include a bounded `error.type` on failures and omit it on success, but verify the domain-specific group.
- Do not model an OTel metric as one ECS document field. Preserve metric name, data point, instrument/aggregation semantics, unit, dimensions, resource, temporality, and timestamps through the export/storage layer.
- Test no-error/error series, attribute-set stability, unit conversion, monotonicity, delta/cumulative handling where relevant, and cardinality bounds.

## Resources and entities

- Use resource/entity conventions for the entity producing or owning telemetry, not for per-operation details.
- Verify identity fields, required identifying attributes, and entity type/group before adding descriptive metadata.
- Keep SDK/scope identity distinct from service identity and collector/observer identity.
- Decide which layer performs ECS reuse or nesting, such as host, service, cloud, container, or orchestrator placement.
- Test merge precedence between SDK detectors, user configuration, collector enrichment, and backend ingest.

## ECS event storage

- Populate `@timestamp` with event origin time and distinguish `event.created`, `event.ingested`, `event.start`, `event.end`, and `event.duration`.
- Populate `ecs.version` for the ECS contract used by the producer or mapping.
- Select `event.kind`, `event.category`, `event.type`, and `event.outcome` from their documented meanings and allowed values; do not infer them from log level.
- Use source/destination, client/server, host/observer/agent, service, and related fieldsets according to ECS role guidance.
- Respect field types, keyword/text conventions, expected arrays, field reuse, allowed values, and nanosecond duration units.
- Preserve `event.original` or `log.original` only according to the relevant guidance and retention/privacy requirements.
- Add custom fields only after searching ECS and OTel; avoid defining arbitrary children beneath a standard ECS object.

## ECS and OTel interoperability

Use the ECS schema's `otel:` metadata as a compatibility statement, not as permission to copy values blindly.

| Relation     | Implementation decision                                                                       |
| ------------ | --------------------------------------------------------------------------------------------- |
| `match`      | Share the semantic value only after verifying the current OTel group, type, and placement.    |
| `equivalent` | Rename or alias when both storage representations and types are compatible; test round trips. |
| `related`    | Define a transform and document preconditions and information loss.                           |
| `conflict`   | Keep both or choose one contract explicitly; never silently alias.                            |
| `metric`     | Convert through a metric-aware pipeline, not a field rename.                                  |
| `otlp`       | Map protocol-native context or record fields at export/ingest.                                |
| `na`         | Keep ECS-specific data separate from OTel standard namespaces.                                |

Check all mappings twice when versions differ: once against ECS's pinned SemConv ref and once against the actual instrumentation target. A newer OTel convention may add, rename, stabilize, or deprecate an item after ECS generated its mapping.

## Verification matrix

Cover the applicable rows in emitted OTLP or stored ECS fixtures:

| Case                      | Verify                                                                                        |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| Normal success            | Required/default fields, correct absence of error data, stable names and types.               |
| Domain error              | Status/outcome, bounded error classification, no duplicate exception emission.                |
| Missing conditional input | Omit conditionally required data only when its condition is false.                            |
| Opt-in disabled/enabled   | No costly or sensitive data by default; exact fields after explicit enablement.               |
| Unknown/custom value      | Follow `_OTHER`, custom value, or omission rules from the exact convention.                   |
| Resource enrichment       | Correct entity placement and deterministic merge precedence.                                  |
| ECS transform             | Correct relation type, type/unit conversion, arrays, timestamps, and correlation IDs.         |
| Version migration         | Stable default behavior, configured experimental/dual emission, and deprecated-name handling. |
