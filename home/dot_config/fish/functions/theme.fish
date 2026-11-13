function theme --description "Show or change the dotfiles theme"
    command theme $argv
    and fish_config theme choose (chezmoi --skip-secrets execute-template '{{ template "theme" . }}')
end
