if status is-interactive
  set -U fish_greeting

  source $__fish_config_dir/conf.d/shortcuts.fish
  source $__fish_config_dir/conf.d/fish-ssh-agent.fish

  function h
       set _h_dir ($__fish_config_dir/bin/h --resolve "/Users/$USER/repos" $argv)
       set _h_ret $status
       if test "$_h_dir" != "$PWD"
           cd "$_h_dir"
       end
       return $_h_ret
  end

  fzf_configure_bindings --directory=\ct

  if command -q zoxide
    zoxide init fish | source
  end

  if command -q atuin
    atuin init fish | source
  end

  if command -q direnv
    direnv hook fish | source
  end
end

# Added by OrbStack: command-line tools and integration
# This won't be added again if you remove it.
source ~/.orbstack/shell/init2.fish 2>/dev/null || :
