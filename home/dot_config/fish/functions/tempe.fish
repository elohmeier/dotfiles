function tempe --description "Start a Fish subshell in a new temporary directory"
    set -l directory (mktemp -d)
    and fish --init-command "cd -- "(string escape -- "$directory")
end
