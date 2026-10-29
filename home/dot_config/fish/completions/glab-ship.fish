complete -c glab-ship -f -a '(env _GLAB_SHIP_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) glab-ship | string replace -r "^plain," "")'
