function _wt_complete
    _wt_worktrees | while read --local --delimiter \t directory branch
        if test "$branch" = 'detached HEAD'
            printf '%s\tdetached HEAD\n' "$directory"
        else
            printf '%s\t%s\n' "$branch" "$directory"
        end
    end
end

complete -c wt -f -n '__fish_is_nth_token 1' -a '(_wt_complete)'
