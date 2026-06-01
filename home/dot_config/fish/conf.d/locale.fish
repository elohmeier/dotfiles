# Force UTF-8 locale so tmux and other tools don't strip multibyte chars.
# Without this, macOS Terminal/Ghostty start fish with LANG="" / LC_CTYPE=C,
# and tmux renders accented chars (é, ü, …) as `_`.
set -gx LANG en_US.UTF-8
