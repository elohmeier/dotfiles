#!/bin/bash

set -uo pipefail

if ! command -v apt-get &>/dev/null; then
    exit 0
fi

sudo apt-get update
sudo apt-get install -y desktop-file-utils wslu xdg-utils
