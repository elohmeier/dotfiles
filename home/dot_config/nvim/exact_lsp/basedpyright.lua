return {
  cmd = { "basedpyright-langserver", "--stdio" },
  filetypes = { "python" },
  root_markers = {
    { "pyrightconfig.json", "pyproject.toml", "Pipfile", "requirements.txt", "setup.cfg", "setup.py" },
    ".git",
  },
  settings = {
    basedpyright = {
      analysis = {
        typeCheckingMode = "standard",
      },
    },
  },
}
