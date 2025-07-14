#!/bin/bash
#
# Detects display configuration by checking if external displays are connected.
# Returns 'external' when external displays are connected.
# Returns 'internal' when only built-in displays are in use.

set -euo pipefail

# Check if yq (go-yq) is installed
HAS_YQ=true
if ! command -v yq &> /dev/null; then
    HAS_YQ=false
fi

# Get display information in JSON format.
# We redirect stderr to /dev/null to avoid printing errors if the command fails.
display_json=$(system_profiler -json SPDisplaysDataType 2>/dev/null || echo "{}")

# If yq is not available, fall back to internal display assumption
if [ "$HAS_YQ" = "false" ]; then
  echo -n "internal"
  exit 0
fi

# Count displays where the connection type is not internal.
# We use '|| echo -n ""' to ensure that we get a count of 0 if yq fails.
external_displays_count=$( (echo "${display_json}" | yq '.SPDisplaysDataType[].spdisplays_ndrvs[] | select(.spdisplays_connection_type != "spdisplays_internal") | ._name' 2>/dev/null || echo -n "") | wc -l)

if [ "${external_displays_count}" -gt 0 ]; then
  echo -n "external"
else
  echo -n "internal"
fi
