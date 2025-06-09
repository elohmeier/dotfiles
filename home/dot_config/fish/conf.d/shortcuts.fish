abbr --add -- cd.. 'cd ..'
abbr --add -- e nvim
abbr --add -- ga 'git add'
abbr --add -- ga. 'git add .'
abbr --add -- gb 'git branch'
abbr --add -- gc 'git commit'
abbr --add -- gcf 'git commit --fixup'
abbr --add -- gco 'git checkout'
abbr --add -- gcp 'git cherry-pick'
abbr --add -- gd 'git diff'
abbr --add -- gf 'git fetch'
abbr --add -- gl 'git log'
abbr --add -- gp 'git pull'
abbr --add -- gpp 'git push'
abbr --add -- gst 'git status'
abbr --add -- kc kubectl
abbr --add -- nb 'nix build'
abbr --add -- nf 'nix flake'
abbr --add -- nfl 'nix flake lock'
abbr --add -- nfu 'nix flake update'
abbr --add -- nr 'nix run'
abbr --add -- y yazi

alias gaapf 'git add . && git commit --amend --no-edit && git push --force-with-lease'
alias gapf 'git commit --amend --no-edit && git push --force-with-lease'
alias gg lazygit
alias grep 'grep --color'
alias l 'eza -al'
alias la 'eza -al'
alias lg 'eza -al --git'
alias lgg lazygit
alias ll 'eza -l'
alias ls eza
alias nbconvert 'jupyter nbconvert --to script --stdout'
alias tree 'eza --tree'
alias vi nvim
alias vim nvim

# Only use orb for nix if nix is not directly available but orb is
if not command -q nix; and command -q orb
    alias nix 'orb nix --extra-experimental-features "nix-command flakes"'
end
