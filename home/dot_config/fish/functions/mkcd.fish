function mkcd --argument-names directory --description "Create a directory and enter it"
    mkdir -p -- "$directory"
    and cd -- "$directory"
end
