return {
  cmd = { "rust-analyzer" },
  filetypes = { "rust" },
  root_markers = { "Cargo.toml", "rust-project.json", ".git" },
  settings = {
    ["rust-analyzer"] = {
      cargo = {
        features = "all",
        buildScripts = { enable = false },
        extraEnv = {
          CMAKE_POLICY_VERSION_MINIMUM = "3.5",
        },
      },
      check = { extraArgs = { "--offline" } },
      diagnostics = {
        disabled = { "unresolved-proc-macro" },
      },
    },
  },
}
