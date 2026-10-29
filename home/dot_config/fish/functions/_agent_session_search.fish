function _agent_session_search --description 'Search agent sessions and insert the resume command'
    set -l selected (agent-session --print | string collect)
    if test $status -eq 0; and test -n "$selected"
        commandline --replace -- $selected
    end
    commandline --function repaint
end
