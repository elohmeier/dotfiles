complete -c glab-deploy -f -a '(env _GLAB_DEPLOY_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) glab-deploy | string replace -r "^plain," "")'
