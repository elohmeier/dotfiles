function scratch --description "Open a temporary file in the editor"
    set -l file (mktemp)
    and $EDITOR "$file"
end
