function wt --argument-names target --description "Open a Git worktree in a Fish subshell"
    set -l worktrees (_wt_worktrees)
    if not set -q worktrees[1]
        echo 'wt: no available worktrees in the current repository' >&2
        return 1
    end

    set -l directory
    if test -z "$target"
        set -l selected (printf '%s\n' $worktrees | fzf --delimiter \t --with-nth 2,1 --prompt 'Worktree> ' --select-1)
        or return
        set directory (string split --fields 1 \t -- "$selected")
    else
        for worktree in $worktrees
            set -l fields (string split --max 1 \t -- "$worktree")
            if test "$target" = "$fields[1]"; or test "$target" = "$fields[2]"
                set -a directory "$fields[1]"
            end
        end
        if test (count $directory) -ne 1
            echo "wt: no unique worktree for '$target'; use Tab or the picker" >&2
            return 1
        end
    end
    fish --init-command "cd -- "(string escape -- "$directory")
end
