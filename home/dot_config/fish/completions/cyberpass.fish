function __cyberpass_entries
    cyberpass ls --flat 2>/dev/null
end

set -l cmds ls find show edit
complete -c cyberpass -f
complete -c cyberpass -l help -d 'Show help'
complete -c cyberpass -n "not __fish_seen_subcommand_from $cmds" -a ls -d 'List entries'
complete -c cyberpass -n "not __fish_seen_subcommand_from $cmds" -a find -d 'Find entries by name'
complete -c cyberpass -n "not __fish_seen_subcommand_from $cmds" -a show -d 'Show entry'
complete -c cyberpass -n "not __fish_seen_subcommand_from $cmds" -a edit -d 'Edit entry in $EDITOR'
complete -c cyberpass -n "not __fish_seen_subcommand_from $cmds" -a '(__cyberpass_entries)'
complete -c cyberpass -n "__fish_seen_subcommand_from show edit" -a '(__cyberpass_entries)'
complete -c cyberpass -n "__fish_seen_subcommand_from ls" -a '(__cyberpass_entries | string replace -r "/.*" "/" | sort -u)'
complete -c cyberpass -n "not __fish_seen_subcommand_from ls find edit" -s c -l clip -d 'Copy password to clipboard'
complete -c cyberpass -n "not __fish_seen_subcommand_from ls find" -s r -l reason -r -d 'Reason for password access'
