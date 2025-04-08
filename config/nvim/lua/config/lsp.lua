vim.lsp.config["luals"] = {
  cmd = { "lua-language-server" },
  filetypes = { "lua" },
  -- Sets the "root directory" to the parent directory of the file in the
  -- current buffer that contains either a ".luarc.json" or a
  -- ".luarc.jsonc" file. Files that share a root directory will reuse
  -- the connection to the same LSP server.
  root_markers = { ".luarc.json", ".luarc.jsonc" },
  offset_encoding = "utf-8",
  -- Specific settings to send to the server. The schema for this is
  -- defined by the server. For example the schema for lua-language-server
  -- can be found here https://raw.githubusercontent.com/LuaLS/vscode-lua/master/setting/schema.json
  settings = {
    Lua = {
      diagnostics = {
        globals = { "vim" },
      },
      runtime = {
        version = "LuaJIT",
      },
    },
  },
}

vim.lsp.config["bashls"] = {
  cmd = { "bash-language-server", "start" },
  filetypes = { "bash", "sh" },
  single_file_support = true,
  offset_encoding = "utf-8",
}

vim.lsp.config["jsonnet_ls"] = {
  cmd = { "jsonnet-language-server" },
  filetypes = { "jsonnet", "libsonnet" },
  single_file_support = true,
  root_markers = { "jsonnetfile.json" },
  offset_encoding = "utf-8",
}

vim.lsp.config["ruff_lsp"] = {
  cmd = { "ruff", "server" },
  filetypes = { "python" },
  root_markers = { "pyproject.toml", "ruff.toml", ".ruff.toml", ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
  settings = {},
}

vim.lsp.config["basedpyright"] = {
  cmd = { "basedpyright-langserver", "--stdio" },
  filetypes = { "python" },
  root_markers = {
    ".git",
    ".ruff.toml",
    "Pipfile",
    "pyproject.toml",
    "pyrightconfig.json",
    "requirements.txt",
    "ruff.toml",
    "setup.cfg",
    "setup.py",
  },
  single_file_support = true,
  offset_encoding = "utf-8",
  settings = {
    basedpyright = {
      analysis = {
        autoSearchPaths = true,
        useLibraryCodeForTypes = true,
      },
      typeCheckingMode = "standard",
    },
  },
}

vim.lsp.enable("luals")
vim.lsp.enable("bashls")
vim.lsp.enable("jsonnet_ls")
vim.lsp.enable("ruff_lsp")
vim.lsp.enable("basedpyright")

vim.diagnostic.config({ virtual_lines = {
  current_line = false,
} })

-- LSP keymaps
-- Rename
vim.keymap.set("n", "<leader>vrn", function()
  vim.lsp.buf.rename()
end, { desc = "Rename", silent = true })

-- Go to next diagnostic (warning or higher) without floating window
vim.keymap.set("n", "]d", function()
  vim.diagnostic.goto_next({
    severity = { min = vim.diagnostic.severity.WARN },
    float = false, -- Disable the floating window
  })
end, { desc = "Next Diagnostic", silent = true })

-- Go to previous diagnostic (warning or higher) without floating window
vim.keymap.set("n", "[d", function()
  vim.diagnostic.goto_prev({
    severity = { min = vim.diagnostic.severity.WARN },
    float = false, -- Disable the floating window
  })
end, { desc = "Previous Diagnostic", silent = true })

-- Go to definition
vim.keymap.set("n", "<C-k>", "<cmd>lua vim.lsp.buf.definition()<CR>", { desc = "Goto Definition", silent = true })
