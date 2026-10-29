#!/bin/sh
set -e

chezmoi apply --source-path "$(chezmoi source-path)/.chezmoiscripts/run_onchange_before_install-packages.sh.tmpl"
exec chezmoi apply
