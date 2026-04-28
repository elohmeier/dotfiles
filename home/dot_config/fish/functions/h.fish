function h
    set -l dir ($HOME/.local/bin/h $argv)
    set -l ret $status
    test "$dir" != "$PWD"; and cd "$dir"
    return $ret
end
