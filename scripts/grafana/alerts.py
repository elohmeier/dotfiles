from __future__ import annotations

import copy
import difflib
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote

import httpx
import rich_click as click
import yaml

from .common import (
    ALERT_RULE_API_VERSION,
    ALERT_RULE_FOLDER_KEY,
    ALERT_RULE_GROUP_KEY,
    ALERT_RULE_KIND,
    ALERT_RULE_MANAGER_ANNOTATIONS,
    ALERT_RULE_PATCH_CONTENT_TYPES,
    ALERT_RULE_PROVISIONING_PATH,
    ALERT_RULE_SERVER_ANNOTATIONS,
    ALERT_RULE_SERVER_METADATA_FIELDS,
    ALERT_RULES_APP_PATH,
    ELASTICSEARCH_EXPLORE_LINK_END,
    ELASTICSEARCH_EXPLORE_LINK_LABEL,
    ELASTICSEARCH_EXPLORE_LINK_RE,
    ELASTICSEARCH_EXPLORE_LINK_START,
    ELASTICSEARCH_EXPLORE_QUERY_SENTINEL,
    ELASTICSEARCH_LEGACY_EXPLORE_LINK_RE,
    REQUEST_EXTENSIONS,
)


@dataclass(slots=True, frozen=True)
class ElasticsearchAlertQuery:
    ref_id: str
    datasource_uid: str
    model: dict[str, Any]
    term_fields: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ExploreLinkChange:
    name: str
    title: str
    rule: dict[str, Any]
    query: ElasticsearchAlertQuery
    description: str


def alert_rule_path(namespace: str, name: str | None = None) -> str:
    path = ALERT_RULES_APP_PATH.format(namespace=quote(namespace, safe=""))
    return f"{path}/{quote(name, safe='')}" if name else path


def load_document(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise click.UsageError(f"invalid JSON/YAML in {path}: {e}") from e


def print_response(r: httpx.Response) -> int:
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    if not r.content:
        return 0
    try:
        body = r.json()
    except json.JSONDecodeError:
        print(r.text)
    else:
        print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0


def fetch_alert_rule(
    c: httpx.Client, namespace: str, name: str
) -> tuple[dict[str, Any] | None, int]:
    r = c.get(
        alert_rule_path(namespace, name),
        extensions=REQUEST_EXTENSIONS,
    )
    if r.status_code >= 400:
        return None, print_response(r)
    body = r.json()
    if not isinstance(body, dict):
        raise click.ClickException("Grafana returned a non-object alert rule")
    return cast(dict[str, Any], body), 0


def fetch_alert_rules(c: httpx.Client, namespace: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    continue_token: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": 1000}
        if continue_token:
            params["continue"] = continue_token
        response = c.get(
            alert_rule_path(namespace),
            params=params,
            extensions=REQUEST_EXTENSIONS,
        )
        if response.status_code >= 400:
            raise click.ClickException(
                f"Grafana returned HTTP {response.status_code}: {response.text}"
            )
        body = response.json()
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise click.ClickException("Grafana returned an invalid alert-rule list")
        rules.extend(cast(list[dict[str, Any]], items))
        metadata = body.get("metadata", {})
        continue_token = (
            metadata.get("continue") if isinstance(metadata, dict) else None
        )
        if not isinstance(continue_token, str) or not continue_token:
            return rules


def elasticsearch_alert_query(
    rule: dict[str, Any], datasource_uids: frozenset[str]
) -> ElasticsearchAlertQuery | None:
    spec = rule.get("spec")
    expressions = spec.get("expressions") if isinstance(spec, dict) else None
    if not isinstance(expressions, dict):
        return None

    matches: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
    for ref_id, expression_value in expressions.items():
        if not isinstance(ref_id, str) or not isinstance(expression_value, dict):
            continue
        expression = cast(dict[str, Any], expression_value)
        model_value = expression.get("model")
        if not isinstance(model_value, dict):
            continue
        model = cast(dict[str, Any], model_value)
        datasource = model.get("datasource")
        if (
            not isinstance(datasource, dict)
            or datasource.get("type") != "elasticsearch"
        ):
            continue
        datasource_uid = expression.get("datasourceUID") or datasource.get("uid")
        if not isinstance(datasource_uid, str) or not datasource_uid:
            raise ValueError(
                f"Elasticsearch expression {ref_id!r} has no datasource UID"
            )
        if datasource_uids and datasource_uid not in datasource_uids:
            continue
        matches.append((ref_id, expression, model, datasource_uid))

    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("has multiple Elasticsearch queries")

    ref_id, expression, model, datasource_uid = matches[0]
    query_type = model.get("queryType") or expression.get("queryType") or "lucene"
    if query_type != "lucene":
        raise ValueError(
            f"Elasticsearch expression {ref_id!r} uses unsupported query type {query_type!r}"
        )
    if model.get("hide") is True:
        raise ValueError(f"Elasticsearch expression {ref_id!r} is hidden")
    if not isinstance(model.get("query", ""), str):
        raise ValueError(f"Elasticsearch expression {ref_id!r} has no string query")

    bucket_aggs = model.get("bucketAggs", [])
    term_fields: list[str] = []
    if isinstance(bucket_aggs, list):
        for aggregation in bucket_aggs:
            if not isinstance(aggregation, dict) or aggregation.get("type") != "terms":
                continue
            field_name = aggregation.get("field")
            if (
                isinstance(field_name, str)
                and field_name
                and field_name not in term_fields
            ):
                term_fields.append(field_name)
    return ElasticsearchAlertQuery(
        ref_id=ref_id,
        datasource_uid=datasource_uid,
        model=model,
        term_fields=tuple(term_fields),
    )


def go_template_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def lucene_escape_term(value: str) -> str:
    value = re.sub(r"(&&|\|\||[+\-!(){}\[\]^\"~*?:\\/])", r"\\\1", value)
    return re.sub(r"\s", lambda match: "\\" + match.group(), value)


def build_elasticsearch_explore_link(query: ElasticsearchAlertQuery) -> str:
    model = query.model
    runtime_query = str(model.get("query", ""))
    parts = [
        ELASTICSEARCH_EXPLORE_LINK_START,
        f"{{{{ $query := {go_template_string(runtime_query)} }}}}",
        '{{ $from := ("-30m" | parseDuration | toDuration | (now | toTime).Add).UnixMilli }}',
        "{{ $to := (now | toTime).UnixMilli }}",
    ]
    for field_name in query.term_fields:
        escaped_field = lucene_escape_term(field_name).replace("%", "%%")
        filter_format = go_template_string(f"%s AND {escaped_field}:%q")
        label = go_template_string(field_name)
        parts.append(
            f"{{{{ with $value := index $labels {label} }}}}"
            f"{{{{ $query = printf {filter_format} $query $value }}}}"
            "{{ end }}"
        )

    explore_query: dict[str, Any] = {
        "refId": query.ref_id,
        "datasource": {"type": "elasticsearch", "uid": query.datasource_uid},
        "query": ELASTICSEARCH_EXPLORE_QUERY_SENTINEL,
        "queryType": "lucene",
        "metrics": [{"id": "1", "type": "logs", "settings": {"limit": "500"}}],
        "bucketAggs": [],
    }
    for field_name in ("editorType", "timeField"):
        value = model.get(field_name)
        if isinstance(value, str) and value:
            explore_query[field_name] = value
    panes = {
        "log": {
            "datasource": query.datasource_uid,
            "queries": [explore_query],
            "range": {"from": "grafana-query-from", "to": "grafana-query-to"},
        }
    }
    panes_format = json.dumps(panes, ensure_ascii=False, separators=(",", ":"))
    panes_format = (
        panes_format.replace("%", "%%")
        .replace(go_template_string(ELASTICSEARCH_EXPLORE_QUERY_SENTINEL), "%q")
        .replace(go_template_string("grafana-query-from"), '"%d"')
        .replace(go_template_string("grafana-query-to"), '"%d"')
    )
    parts.extend(
        (
            f"{{{{ $panes := printf {go_template_string(panes_format)} $query $from $to }}}}",
            f"{ELASTICSEARCH_EXPLORE_LINK_LABEL} "
            "{{ externalURL }}explore?schemaVersion=1&panes="
            "{{ $panes | urlquery }}&orgId=1",
            ELASTICSEARCH_EXPLORE_LINK_END,
        )
    )
    return "".join(parts)


def reconcile_elasticsearch_explore_description(
    description: str, explore_link: str
) -> str:
    start_count = description.count(ELASTICSEARCH_EXPLORE_LINK_START)
    end_count = description.count(ELASTICSEARCH_EXPLORE_LINK_END)
    if start_count != end_count or start_count > 1:
        raise ValueError("description has malformed managed Explore-link markers")
    if start_count:
        return ELASTICSEARCH_EXPLORE_LINK_RE.sub(explore_link, description)

    description = ELASTICSEARCH_LEGACY_EXPLORE_LINK_RE.sub("", description)
    description = description.rstrip("\n")
    return f"{description}\n{explore_link}" if description else explore_link


def prepare_alert_rule(
    source: Any,
    namespace: str,
    name: str | None = None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise click.UsageError("alert rule must be a JSON/YAML object")
    rule = copy.deepcopy(cast(dict[str, Any], source))
    if rule.get("apiVersion") != ALERT_RULE_API_VERSION:
        raise click.UsageError(
            f"alert rule apiVersion must be {ALERT_RULE_API_VERSION}"
        )
    if rule.get("kind") != ALERT_RULE_KIND:
        raise click.UsageError(f"alert rule kind must be {ALERT_RULE_KIND}")
    if not isinstance(rule.get("spec"), dict):
        raise click.UsageError("alert rule spec must be an object")

    metadata = rule.get("metadata")
    if not isinstance(metadata, dict):
        raise click.UsageError("alert rule metadata must be an object")
    metadata = cast(dict[str, Any], metadata)
    source_name = metadata.get("name")
    if name and source_name not in (None, name):
        raise click.UsageError(
            f"alert rule metadata.name {source_name!r} does not match {name!r}"
        )
    metadata["name"] = name or source_name
    if not isinstance(metadata["name"], str) or not metadata["name"]:
        raise click.UsageError("alert rule metadata.name is required")
    source_namespace = metadata.get("namespace")
    if source_namespace not in (None, namespace):
        raise click.UsageError(
            f"alert rule metadata.namespace {source_namespace!r} does not match {namespace!r}"
        )
    metadata["namespace"] = namespace

    for metadata_field in ALERT_RULE_SERVER_METADATA_FIELDS:
        metadata.pop(metadata_field, None)
    rule.pop("status", None)
    annotations = metadata.setdefault("annotations", {})
    if not isinstance(annotations, dict):
        raise click.UsageError("alert rule metadata.annotations must be an object")
    for annotation in ALERT_RULE_SERVER_ANNOTATIONS:
        annotations.pop(annotation, None)

    if current is None:
        metadata.pop("resourceVersion", None)
        return rule

    current_metadata = current.get("metadata", {})
    if not isinstance(current_metadata, dict):
        raise click.ClickException("Grafana returned invalid alert-rule metadata")
    if "resourceVersion" not in metadata and current_metadata.get("resourceVersion"):
        metadata["resourceVersion"] = current_metadata["resourceVersion"]
    current_annotations = current_metadata.get("annotations", {})
    if not isinstance(current_annotations, dict):
        raise click.UsageError("alert rule metadata.annotations must be an object")
    for key in ALERT_RULE_MANAGER_ANNOTATIONS:
        if key in current_annotations:
            annotations.setdefault(key, current_annotations[key])
    return rule


_PROM_DURATION_RE = re.compile(
    r"^(?:(?P<y>[0-9]+)y)?(?:(?P<w>[0-9]+)w)?(?:(?P<d>[0-9]+)d)?"
    r"(?:(?P<h>[0-9]+)h)?(?:(?P<m>[0-9]+)m)?(?:(?P<s>[0-9]+)s)?$"
)
_PROM_DURATION_UNIT_SECONDS = {
    "y": 365 * 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}


def parse_prom_duration_seconds(value: Any, field_name: str) -> int:
    if value == "0":
        return 0
    if not isinstance(value, str) or not value:
        raise click.UsageError(f"{field_name} must be a Prometheus duration")
    match = _PROM_DURATION_RE.fullmatch(value)
    if match is None or not any(match.groupdict().values()):
        raise click.UsageError(
            f"{field_name} has invalid Prometheus duration {value!r}"
        )
    return sum(
        int(amount) * _PROM_DURATION_UNIT_SECONDS[unit]
        for unit, amount in match.groupdict().items()
        if amount is not None
    )


def app_alert_rule_to_provisioning(rule: dict[str, Any]) -> dict[str, Any]:
    metadata = cast(dict[str, Any], rule["metadata"])
    spec = cast(dict[str, Any], rule["spec"])
    annotations = metadata.get("annotations", {})
    labels = metadata.get("labels", {})
    if not isinstance(annotations, dict) or not isinstance(labels, dict):
        raise click.UsageError("alert rule metadata labels/annotations must be objects")

    folder_uid = annotations.get(ALERT_RULE_FOLDER_KEY) or labels.get(
        ALERT_RULE_FOLDER_KEY
    )
    if not isinstance(folder_uid, str) or not folder_uid:
        raise click.UsageError(
            f"alert rule metadata must set {ALERT_RULE_FOLDER_KEY!r}"
        )
    group = labels.get(ALERT_RULE_GROUP_KEY)
    if not isinstance(group, str) or not group:
        raise click.UsageError(
            f"alert rule metadata.labels must set {ALERT_RULE_GROUP_KEY!r}"
        )

    expressions = spec.get("expressions")
    if not isinstance(expressions, dict) or not expressions:
        raise click.UsageError("alert rule spec.expressions must be a non-empty object")
    condition: str | None = None
    data: list[dict[str, Any]] = []
    for ref_id, expression_value in expressions.items():
        if not isinstance(ref_id, str) or not ref_id:
            raise click.UsageError(
                "alert rule expression IDs must be non-empty strings"
            )
        if not isinstance(expression_value, dict):
            raise click.UsageError(
                f"alert rule expression {ref_id!r} must be an object"
            )
        expression = cast(dict[str, Any], expression_value)
        if expression.get("source") is True:
            if condition is not None:
                raise click.UsageError(
                    f"multiple alert rule expressions are marked source: "
                    f"{condition!r} and {ref_id!r}"
                )
            condition = ref_id
        relative_range = expression.get("relativeTimeRange", {})
        if not isinstance(relative_range, dict):
            raise click.UsageError(
                f"alert rule expression {ref_id!r} relativeTimeRange must be an object"
            )
        data.append(
            {
                "refId": ref_id,
                "queryType": expression.get("queryType", ""),
                "relativeTimeRange": {
                    "from": parse_prom_duration_seconds(
                        relative_range.get("from", "0s"),
                        f"expression {ref_id} relativeTimeRange.from",
                    ),
                    "to": parse_prom_duration_seconds(
                        relative_range.get("to", "0s"),
                        f"expression {ref_id} relativeTimeRange.to",
                    ),
                },
                "datasourceUid": expression.get("datasourceUID", "__expr__"),
                "model": expression.get("model", {}),
            }
        )
    if condition is None:
        raise click.UsageError(
            "exactly one alert rule expression must set source: true"
        )

    no_data_states = {
        "Ok": "OK",
        "NoData": "NoData",
        "Alerting": "Alerting",
        "KeepLast": "KeepLast",
    }
    exec_err_states = {
        "Ok": "OK",
        "Error": "Error",
        "Alerting": "Alerting",
        "KeepLast": "KeepLast",
    }
    no_data_state = spec.get("noDataState", "NoData")
    exec_err_state = spec.get("execErrState", "Error")
    if no_data_state not in no_data_states:
        raise click.UsageError(f"invalid alert rule noDataState {no_data_state!r}")
    if exec_err_state not in exec_err_states:
        raise click.UsageError(f"invalid alert rule execErrState {exec_err_state!r}")

    body: dict[str, Any] = {
        "uid": metadata["name"],
        "folderUID": folder_uid,
        "ruleGroup": group,
        "title": spec.get("title", ""),
        "condition": condition,
        "data": data,
        "noDataState": no_data_states[no_data_state],
        "execErrState": exec_err_states[exec_err_state],
        "for": spec.get("for", "0s"),
        "annotations": spec.get("annotations", {}),
        "labels": spec.get("labels", {}),
        "isPaused": spec.get("paused", False),
    }
    if "keepFiringFor" in spec:
        body["keep_firing_for"] = spec["keepFiringFor"]
    if "missingSeriesEvalsToResolve" in spec:
        body["missingSeriesEvalsToResolve"] = spec["missingSeriesEvalsToResolve"]

    notification_settings = spec.get("notificationSettings")
    if notification_settings is not None:
        if not isinstance(notification_settings, dict):
            raise click.UsageError(
                "alert rule spec.notificationSettings must be an object"
            )
        if notification_settings.get("type") != "SimplifiedRouting":
            raise click.UsageError(
                "create supports only SimplifiedRouting notification settings"
            )
        field_names = {
            "receiver": "receiver",
            "groupBy": "group_by",
            "groupWait": "group_wait",
            "groupInterval": "group_interval",
            "repeatInterval": "repeat_interval",
            "muteTimeIntervals": "mute_time_intervals",
            "activeTimeIntervals": "active_time_intervals",
        }
        body["notification_settings"] = {
            target: notification_settings[source]
            for source, target in field_names.items()
            if source in notification_settings
        }
    return body


def alert_rule_manager(rule: dict[str, Any]) -> str | None:
    metadata = rule.get("metadata", {})
    annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
    if not isinstance(annotations, dict):
        return None
    manager = annotations.get("grafana.app/managedBy")
    provenance = annotations.get("grafana.com/provenance")
    if manager:
        return f"managed by {manager}"
    if provenance:
        return f"provenance {provenance}"
    return None


def check_alert_rule_manager(rule: dict[str, Any], allow_managed: bool) -> None:
    manager = alert_rule_manager(rule)
    if manager and not allow_managed:
        raise click.UsageError(
            f"alert rule is {manager}; pass --allow-managed to modify it"
        )


def mutate_alert_rule(
    c: httpx.Client,
    method: str,
    path: str,
    content: bytes | None,
    content_type: str | None,
    prompt: str,
    dry_run: bool,
    yes: bool,
    strict: bool = True,
    extra_params: dict[str, str | bool] | None = None,
) -> int:
    params: dict[str, str | bool] = dict(extra_params or {})
    if strict:
        params["fieldValidation"] = "Strict"
    headers = {"Content-Type": content_type} if content_type else None

    if dry_run:
        print(
            "Dry run: local validation passed; no write request sent.", file=sys.stderr
        )
        return 0

    if not yes and not click.confirm(prompt):
        print("Cancelled.", file=sys.stderr)
        return 0
    response = c.request(
        method,
        path,
        params=params,
        content=content,
        headers=headers,
        extensions=REQUEST_EXTENSIONS,
    )
    return print_response(response)


def json_content(body: Any) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode()


def cmd_alert_rule_get(c: httpx.Client, args: Any) -> int:
    rule, result = fetch_alert_rule(c, args.namespace, args.name)
    if rule is not None:
        print(json.dumps(rule, indent=2, ensure_ascii=False))
    return result


def cmd_alert_rule_create(c: httpx.Client, args: Any) -> int:
    rule = prepare_alert_rule(load_document(args.file), args.namespace)
    check_alert_rule_manager(rule, args.allow_managed)
    name = cast(dict[str, Any], rule["metadata"])["name"]
    body = app_alert_rule_to_provisioning(rule)
    if args.dry_run:
        print(
            "Dry run: local validation passed; no write request sent.", file=sys.stderr
        )
        return 0
    if not args.yes and not click.confirm(f"Create alert rule {name}?"):
        print("Cancelled.", file=sys.stderr)
        return 0
    response = c.post(
        ALERT_RULE_PROVISIONING_PATH,
        content=json_content(body),
        headers={
            "Content-Type": "application/json",
            "X-Disable-Provenance": "true",
        },
        extensions=REQUEST_EXTENSIONS,
    )
    if response.status_code >= 400:
        return print_response(response)
    created, result = fetch_alert_rule(c, args.namespace, name)
    if created is not None:
        print(json.dumps(created, indent=2, ensure_ascii=False))
    return result


def cmd_alert_rule_reconcile_explore_links(c: httpx.Client, args: Any) -> int:
    if args.check and args.yes:
        raise click.UsageError("--check and --yes cannot be combined")

    rules = fetch_alert_rules(c, args.namespace)
    datasource_uids = frozenset(args.datasource_uid)
    changes: list[ExploreLinkChange] = []
    errors: list[str] = []
    matched = 0
    unchanged = 0
    managed = 0

    for rule in rules:
        metadata = rule.get("metadata", {})
        spec = rule.get("spec", {})
        name = metadata.get("name") if isinstance(metadata, dict) else None
        title = spec.get("title") if isinstance(spec, dict) else None
        display_name = name if isinstance(name, str) and name else "<unnamed>"
        display_title = title if isinstance(title, str) and title else display_name
        manager = alert_rule_manager(rule)

        try:
            query = elasticsearch_alert_query(rule, datasource_uids)
        except ValueError as error:
            if manager and not args.allow_managed:
                matched += 1
                managed += 1
                print(f"SKIP {display_name}: {display_title} ({manager})")
                continue
            errors.append(f"{display_name}: {error}")
            continue
        if query is None:
            continue
        matched += 1

        if not isinstance(name, str) or not name:
            errors.append(f"{display_name}: has no metadata.name")
            continue
        resource_version = (
            metadata.get("resourceVersion") if isinstance(metadata, dict) else None
        )
        if not isinstance(resource_version, str) or not resource_version:
            errors.append(f"{display_name}: has no metadata.resourceVersion")
            continue
        annotations = spec.get("annotations", {}) if isinstance(spec, dict) else {}
        if not isinstance(annotations, dict):
            errors.append(f"{display_name}: spec.annotations is not an object")
            continue
        description = annotations.get("description", "")
        if not isinstance(description, str):
            errors.append(
                f"{display_name}: spec.annotations.description is not a string"
            )
            continue
        try:
            reconciled = reconcile_elasticsearch_explore_description(
                description,
                build_elasticsearch_explore_link(query),
            )
        except ValueError as error:
            errors.append(f"{display_name}: {error}")
            continue
        if reconciled == description:
            unchanged += 1
            continue

        if manager and not args.allow_managed:
            managed += 1
            print(f"SKIP {name}: {display_title} ({manager})")
            continue
        changes.append(
            ExploreLinkChange(
                name=name,
                title=display_title,
                rule=rule,
                query=query,
                description=reconciled,
            )
        )

    action = "STALE" if args.check else "UPDATE" if args.yes else "WOULD UPDATE"
    for change in changes:
        term_fields = ", ".join(change.query.term_fields) or "none"
        print(
            f"{action} {change.name}: {change.title} "
            f"[datasource={change.query.datasource_uid}, "
            f"query={change.query.ref_id}, terms={term_fields}]"
        )
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    print(
        f"Elasticsearch alert rules: {matched} matched, {len(changes)} changed, "
        f"{unchanged} current, {managed} managed skipped, {len(errors)} errors."
    )
    if errors:
        print("No changes applied because validation failed.", file=sys.stderr)
        return 1
    if args.check:
        return 1 if changes else 0
    if not args.yes:
        if changes:
            print("Preview only; pass --yes to apply these changes.")
        return 0

    failed = 0
    for change in changes:
        content = prepare_alert_rule_patch(
            {"spec": {"annotations": {"description": change.description}}},
            "merge",
            args.namespace,
            change.name,
            change.rule,
        )
        response = c.patch(
            alert_rule_path(args.namespace, change.name),
            params={"fieldValidation": "Strict"},
            content=content,
            headers={
                "Content-Type": ALERT_RULE_PATCH_CONTENT_TYPES["merge"],
            },
            extensions=REQUEST_EXTENSIONS,
        )
        if response.status_code >= 400:
            failed += 1
            print(
                f"ERROR {change.name}: HTTP {response.status_code}: {response.text}",
                file=sys.stderr,
            )
        else:
            print(f"UPDATED {change.name}: {change.title}")
    return 1 if failed else 0


def cmd_alert_rule_replace(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    rule = prepare_alert_rule(
        load_document(args.file),
        args.namespace,
        args.name,
        current,
    )
    check_alert_rule_manager(rule, args.allow_managed)
    return mutate_alert_rule(
        c,
        "PUT",
        alert_rule_path(args.namespace, args.name),
        json_content(rule),
        "application/json",
        f"Replace alert rule {args.name}?",
        args.dry_run,
        args.yes,
    )


def prepare_alert_rule_patch(
    source: Any,
    patch_type: str,
    namespace: str,
    name: str,
    current: dict[str, Any],
) -> bytes:
    metadata = current.get("metadata", {})
    resource_version = (
        metadata.get("resourceVersion") if isinstance(metadata, dict) else None
    )
    if patch_type == "json":
        if not isinstance(source, list):
            raise click.UsageError("JSON patch must be an array")
        patch = copy.deepcopy(source)
        if resource_version:
            patch.insert(
                0,
                {
                    "op": "test",
                    "path": "/metadata/resourceVersion",
                    "value": resource_version,
                },
            )
        return json_content(patch)
    if patch_type == "merge":
        if not isinstance(source, dict):
            raise click.UsageError("merge patch must be an object")
        patch = copy.deepcopy(source)
        patch_metadata = patch.setdefault("metadata", {})
        if not isinstance(patch_metadata, dict):
            raise click.UsageError("merge patch metadata must be an object")
        if resource_version:
            patch_metadata.setdefault("resourceVersion", resource_version)
        return json_content(patch)
    rule = prepare_alert_rule(source, namespace, name)
    return yaml.safe_dump(rule, sort_keys=False).encode()


def cmd_alert_rule_patch(c: httpx.Client, args: Any) -> int:
    if args.force and args.patch_type != "apply":
        raise click.UsageError("--force is supported only with --type apply")
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    content = prepare_alert_rule_patch(
        load_document(args.file),
        args.patch_type,
        args.namespace,
        args.name,
        current,
    )
    params: dict[str, str | bool] = {}
    if args.patch_type == "apply":
        params["fieldManager"] = args.field_manager
        if args.force:
            params["force"] = True
    return mutate_alert_rule(
        c,
        "PATCH",
        alert_rule_path(args.namespace, args.name),
        content,
        ALERT_RULE_PATCH_CONTENT_TYPES[args.patch_type],
        f"Patch alert rule {args.name}?",
        args.dry_run,
        args.yes,
        extra_params=params,
    )


def cmd_alert_rule_edit(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    rule = prepare_alert_rule(current, args.namespace, args.name, current)
    original = json.dumps(rule, indent=2, ensure_ascii=False) + "\n"
    edited = click.edit(original, extension=".json")
    if edited is None:
        print("No changes.", file=sys.stderr)
        return 0
    try:
        edited_rule = prepare_alert_rule(
            json.loads(edited),
            args.namespace,
            args.name,
            current,
        )
    except json.JSONDecodeError as e:
        raise click.UsageError(f"invalid edited JSON: {e}") from e
    check_alert_rule_manager(edited_rule, args.allow_managed)
    if edited_rule == rule:
        print("No changes.", file=sys.stderr)
        return 0

    updated = json.dumps(edited_rule, indent=2, ensure_ascii=False) + "\n"
    sys.stderr.writelines(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"{args.name}.before.json",
            tofile=f"{args.name}.after.json",
        )
    )
    return mutate_alert_rule(
        c,
        "PUT",
        alert_rule_path(args.namespace, args.name),
        json_content(edited_rule),
        "application/json",
        f"Update alert rule {args.name}?",
        args.dry_run,
        args.yes,
    )


def cmd_alert_rule_delete(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    return mutate_alert_rule(
        c,
        "DELETE",
        alert_rule_path(args.namespace, args.name),
        None,
        None,
        f"Delete alert rule {args.name}?",
        args.dry_run,
        args.yes,
        strict=False,
    )
