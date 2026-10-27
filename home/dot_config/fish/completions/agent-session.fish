function _agent_session_completion
    set -l response (env _AGENT_SESSION_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) agent-session)
    for completion in $response
        set -l metadata (string split ',' $completion)
        switch $metadata[1]
            case dir
                __fish_complete_directories $metadata[2]
            case file
                __fish_complete_path $metadata[2]
            case plain
                echo $metadata[2]
        end
    end
end

complete --no-files --command agent-session --arguments '(_agent_session_completion)'
