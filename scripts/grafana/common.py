from __future__ import annotations

import errno
import re

from rich.console import Console

_STEP_RE = re.compile(r"^\s*(\d+)\s*(ms|s|m|h)?\s*$")


_STEP_UNIT_MS = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, None: 1000}


REQUEST_EXTENSIONS: dict[str, str] = {}


CLIENT_DISCONNECT_ERRNOS = {
    errno.ECONNABORTED,
    errno.ECONNRESET,
    errno.EPIPE,
}


DEFAULT_QUERY_API_MAX_BODY_BYTES = 4 * 1024 * 1024


FOLDER_SEARCH_PAGE_SIZE = 1000


ELASTICSEARCH_POST_READ_SUFFIXES = frozenset(
    {
        "/_count",
        "/_field_caps",
        "/_mget",
        "/_msearch",
        "/_render/template",
        "/_search",
        "/_search/template",
        "/_terms_enum",
        "/_validate/query",
    }
)


SHOW_APP_RESOURCES = {
    "alert-rules": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/alertrules",
    "contact-points": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/receivers",
    "inhibition-rules": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/inhibitionrules",
    "mute-timings": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/timeintervals",
    "notification-policies": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/routingtrees",
    "recording-rules": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/recordingrules",
    "rule-sequences": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/rulesequences",
    "templates": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/templategroups",
}


SHOW_FIXED_RESOURCES = {
    "active-alerts": "/api/alertmanager/grafana/api/v2/alerts",
    "contact-point-status": "/api/alertmanager/grafana/config/api/v1/receivers",
    "silences": "/api/alertmanager/grafana/api/v2/silences",
}


SHOW_RESOURCE_ALIASES = {
    "endpoints": "contact-points",
    "notification-rules": "notification-policies",
}


ALERT_RULE_API_VERSION = "rules.alerting.grafana.app/v0alpha1"


ALERT_RULE_KIND = "AlertRule"


ALERT_RULES_APP_PATH = (
    "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/alertrules"
)


ALERT_RULE_PROVISIONING_PATH = "/api/v1/provisioning/alert-rules"


ALERT_RULE_FOLDER_KEY = "grafana.app/folder"


ALERT_RULE_GROUP_KEY = "grafana.com/group"


ALERT_RULE_PATCH_CONTENT_TYPES = {
    "apply": "application/apply-patch+yaml",
    "json": "application/json-patch+json",
    "merge": "application/merge-patch+json",
}


ALERT_RULE_MANAGER_ANNOTATIONS = frozenset(
    {
        "grafana.app/managedBy",
        "grafana.app/managerAllowsEdits",
        "grafana.app/managerId",
        "grafana.app/managerSuspended",
        "grafana.com/provenance",
    }
)


ALERT_RULE_SERVER_METADATA_FIELDS = frozenset(
    {
        "creationTimestamp",
        "deletionGracePeriodSeconds",
        "deletionTimestamp",
        "generation",
        "managedFields",
        "selfLink",
        "uid",
    }
)


ALERT_RULE_SERVER_ANNOTATIONS = frozenset(
    {
        "grafana.app/createdBy",
        "grafana.app/updatedBy",
        "grafana.app/updatedTimestamp",
        "grafana.com/updatedBy",
        "grafana.com/updateTimestamp",
    }
)


ELASTICSEARCH_EXPLORE_LINK_START = (
    "{{/* grafana-query:elasticsearch-explore-link:v1:start */}}"
)


ELASTICSEARCH_EXPLORE_LINK_END = (
    "{{/* grafana-query:elasticsearch-explore-link:v1:end */}}"
)


ELASTICSEARCH_EXPLORE_LINK_LABEL = "Logs (letzte 30 Minuten):"


ELASTICSEARCH_EXPLORE_LINK_RE = re.compile(
    re.escape(ELASTICSEARCH_EXPLORE_LINK_START)
    + ".*?"
    + re.escape(ELASTICSEARCH_EXPLORE_LINK_END),
    re.DOTALL,
)


ELASTICSEARCH_LEGACY_EXPLORE_LINK_RE = re.compile(
    rf"^{re.escape(ELASTICSEARCH_EXPLORE_LINK_LABEL)} .*explore\?[^\n]*(?:\n|$)",
    re.MULTILINE,
)


ELASTICSEARCH_EXPLORE_QUERY_SENTINEL = "grafana-query-runtime-query"


SHOW_RESOURCES = tuple(
    sorted(
        SHOW_APP_RESOURCES.keys()
        | SHOW_FIXED_RESOURCES.keys()
        | SHOW_RESOURCE_ALIASES.keys()
        | {"folders", "teams"}
    )
)


console = Console(stderr=True)


GRAFANA_VERSION = "13.2.2"
