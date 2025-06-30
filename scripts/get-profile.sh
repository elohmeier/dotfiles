#!/bin/bash
#
# Determines if the system is in a 'docked' or 'mobile' state based on connected displays.
# 'docked' means at least one external display is connected.
# 'mobile' means only built-in displays are in use.

set -euo pipefail

# Check if yq (go-yq) is installed
if ! command -v yq &> /dev/null; then
    echo "Error: yq (go-yq) is not installed. Please install it to use this script." >&2
    exit 1
fi

# Get display information in JSON format.
# We redirect stderr to /dev/null to avoid printing errors if the command fails.
display_json=$(system_profiler -json SPDisplaysDataType 2>/dev/null || echo "{}")

# Extract names of displays that are not "Built-in" or "Retina" (case-insensitive)
# and count them.
# The 'test' function in yq performs regex matching.
# We use '|| echo ""' to ensure yq doesn't fail if display_json is empty or invalid,
# which would result in an empty string being piped to wc -l, yielding 0.
external_displays_count=$(echo "${display_json}" | yq '.SPDisplaysDataType[].spdisplays_ndrvs[]._name | select(. | test("Built-in|Retina"; "i") | not)' 2>/dev/null || echo "" | wc -l)

if [ "${external_displays_count}" -gt 0 ]; then
  echo -n "docked"
else
  echo -n "mobile"
fi
