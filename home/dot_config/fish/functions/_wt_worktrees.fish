function _wt_worktrees --description "List available worktree paths and branches"
    set -l directory
    set -l branch
    command git worktree list --porcelain -z 2>/dev/null | while read --null --local field
        switch "$field"
            case 'worktree *'
                set directory (string sub --start 10 -- "$field")
                set branch 'detached HEAD'
            case 'branch refs/heads/*'
                set branch (string replace 'branch refs/heads/' '' -- "$field")
            case bare
                set directory ''
            case ''
                if test -d "$directory"
                    printf '%s\t%s\n' "$directory" "$branch"
                end
        end
    end
end
