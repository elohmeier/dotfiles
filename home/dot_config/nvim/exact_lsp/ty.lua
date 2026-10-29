return {
  cmd = { "ty", "server" },
  filetypes = { "python" },
  root_markers = {
    { "ty.toml", "pyproject.toml", "Pipfile", "requirements.txt", "setup.cfg", "setup.py" },
    ".git",
  },
  settings = {
    ty = {
      completions = {
        autoImport = false,
      },
    },
  },
}
