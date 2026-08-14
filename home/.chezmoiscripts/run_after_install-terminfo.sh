#!/bin/sh
command -v tic >/dev/null 2>&1 && tic -x -o ~/.terminfo ~/.local/share/terminfo/xterm-ghostty.terminfo
