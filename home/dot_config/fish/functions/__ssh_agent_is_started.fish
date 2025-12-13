function __ssh_agent_is_started -d "check if ssh agent is already started"
	command -q ssh-add || return 1

	if test -n "$SSH_CONNECTION"
		ssh-add -l >/dev/null 2>&1
		if test $status -eq 0 -o $status -eq 1
			return 0
		end
	end

	if test -f "$SSH_ENV" -a -z "$SSH_AGENT_PID"
		source $SSH_ENV >/dev/null
	end

	if test -z "$SSH_AGENT_PID"
		return 1
	end

	ssh-add -l >/dev/null 2>&1
	test $status -ne 2
end
