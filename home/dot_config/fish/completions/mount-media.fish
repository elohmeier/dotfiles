complete -c mount-media -f
complete -c mount-media -l help -d 'Show help'
complete -c mount-media -l device -x -d 'Media device' -a '(env _MOUNT_MEDIA_COMPLETE=fish_complete COMP_WORDS="mount-media --device " COMP_CWORD="" mount-media | string replace -r "^plain," "")'
