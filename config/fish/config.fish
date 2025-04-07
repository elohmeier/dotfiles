if status is-interactive
  set -U fish_greeting

  source $__fish_config_dir/conf.d/shortcuts.fish
  source $__fish_config_dir/conf.d/fish-ssh-agent.fish

  function h
       set _h_dir ($__fish_config_dir/bin/h --resolve "/Users/enno/repos" $argv)
       set _h_ret $status
       if test "$_h_dir" != "$PWD"
           cd "$_h_dir"
       end
       return $_h_ret
  end

  zoxide init fish | source

  fzf_configure_bindings --directory=\ct

  atuin init fish | source
  direnv hook fish | source
end

# Added by OrbStack: command-line tools and integration
# This won't be added again if you remove it.
source ~/.orbstack/shell/init2.fish 2>/dev/null || :
