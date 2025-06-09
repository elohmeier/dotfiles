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
  cmd = { "jsonnet-language-server", "--tanka" },
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

vim.lsp.config["tinymist"] = {
  cmd = { "tinymist" },
  filetypes = { "typst" },
  root_markers = { ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
}

vim.lsp.config["tsserver"] = {
  cmd = { "typescript-language-server", "--stdio" },
  filetypes = {
    "javascript",
    "javascriptreact",
    "javascript.jsx",
    "typescript",
    "typescriptreact",
    "typescript.tsx",
  },
  root_markers = { "tsconfig.json", "jsconfig.json", "package.json", ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
  init_options = { hostInfo = "neovim" },
}

vim.lsp.config["terraformls"] = {
  cmd = { "terraform-ls", "serve" },
  filetypes = { "terraform", "terraform-vars" },
  root_markers = { ".terraform", ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
}

vim.lsp.config["svelte"] = {
  cmd = { "svelteserver", "--stdio" },
  filetypes = { "svelte" },
  root_markers = { "package.json", ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
}

vim.lsp.config["helm_ls"] = {
  cmd = { "helm_ls", "serve" },
  filetypes = { "helm" },
  root_markers = { "Chart.yaml" },
  single_file_support = true,
  offset_encoding = "utf-8",
  settings = {
    ["helm-ls"] = {
      yamlls = {
        path = "yaml-language-server",
        enabled = true,
        diagnosticsLimit = 50,
        showDiagnosticsDirectly = false,
        config = {
          schemas = {
            ["https://raw.githubusercontent.com/argoproj/argo-workflows/refs/heads/main/api/jsonschema/schema.json"] = {
              "templates/workflows/*workflowtemplate.yaml",
            },
            kubernetes = {
              "templates/**/*.yaml",
              "!templates/workflows/*workflowtemplate.yaml",
            },
          },
          completion = true,
          hover = true,
        },
      },
    },
  },
}

vim.lsp.enable("luals")
vim.lsp.enable("bashls")
vim.lsp.enable("jsonnet_ls")
vim.lsp.enable("ruff_lsp")
vim.lsp.enable("basedpyright")
vim.lsp.enable("tinymist")
vim.lsp.enable("tsserver")
vim.lsp.enable("terraformls")
vim.lsp.enable("svelte")
vim.lsp.enable("helm_ls")

vim.diagnostic.config({ virtual_lines = {
  current_line = true,
} })

-- Enable document highlight (highlight all instances of word under cursor)
vim.api.nvim_create_autocmd("LspAttach", {
  callback = function(args)
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if client and client.server_capabilities.documentHighlightProvider then
      vim.api.nvim_create_autocmd({ "CursorHold", "CursorHoldI" }, {
        buffer = args.buf,
        callback = vim.lsp.buf.document_highlight,
      })
      vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, {
        buffer = args.buf,
        callback = vim.lsp.buf.clear_references,
      })
    end
  end,
})

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

-- Tinymist commands for Typst
local function create_tinymist_command(command_name)
  local export_type = command_name:match("tinymist%.export(%w+)")
  local info_type = command_name:match("tinymist%.(%w+)")
  if info_type and info_type:match("^get") then
    info_type = info_type:gsub("^get", "Get")
  end
  local cmd_display = export_type or info_type

  local function run_tinymist_command()
    local bufnr = vim.api.nvim_get_current_buf()
    local client = vim.lsp.get_clients({ name = "tinymist", buffer = bufnr })[1]
    if not client then
      return vim.notify("No Tinymist client attached to the current buffer", vim.log.levels.ERROR)
    end
    local arguments = { vim.api.nvim_buf_get_name(bufnr) }
    local title_str = export_type and ("Export " .. cmd_display) or cmd_display

    local function handler(err, res)
      if err then
        return vim.notify(err.code .. ": " .. err.message, vim.log.levels.ERROR)
      end
      -- If exporting, show the string result; else, show the table for inspection
      vim.notify(export_type and res or vim.inspect(res), vim.log.levels.INFO)
    end

    if vim.fn.has("nvim-0.11") == 1 then
      -- For Neovim 0.11+
      return client:exec_cmd({
        title = title_str,
        command = command_name,
        arguments = arguments,
      }, { bufnr = bufnr }, handler)
    else
      return vim.notify("Tinymist commands require Neovim 0.11+", vim.log.levels.WARN)
    end
  end

  -- Construct a readable command name/desc
  local cmd_name = export_type and ("LspTinymistExport" .. cmd_display) or ("LspTinymist" .. cmd_display)
  local cmd_desc = export_type and ("Export to " .. cmd_display) or ("Get " .. cmd_display)
  return run_tinymist_command, cmd_name, cmd_desc
end

-- Create Tinymist commands when a Typst file is opened
vim.api.nvim_create_autocmd("FileType", {
  pattern = "typst",
  callback = function()
    for _, command in ipairs({
      "tinymist.exportSvg",
      "tinymist.exportPng",
      "tinymist.exportPdf",
      "tinymist.exportMarkdown",
      "tinymist.exportText",
      "tinymist.exportQuery",
      "tinymist.exportAnsiHighlight",
      "tinymist.getServerInfo",
      "tinymist.getDocumentTrace",
      "tinymist.getWorkspaceLabels",
      "tinymist.getDocumentMetrics",
    }) do
      local cmd_func, cmd_name, cmd_desc = create_tinymist_command(command)
      vim.api.nvim_create_user_command(cmd_name, cmd_func, { nargs = 0, desc = cmd_desc })
    end
  end,
})

-- Add Svelte 5 migration command
vim.api.nvim_create_user_command("MigrateToSvelte5", function()
  local bufnr = vim.api.nvim_get_current_buf()
  local client = vim.lsp.get_clients({ name = "svelte", buffer = bufnr })[1]
  if not client then
    return vim.notify("No Svelte language server attached to the current buffer", vim.log.levels.ERROR)
  end

  client:exec_cmd({
    command = "migrate_to_svelte_5",
    arguments = { vim.uri_from_bufnr(bufnr) },
  })
end, { desc = "Migrate Component to Svelte 5 Syntax" })

-- Add LspRestart command
vim.api.nvim_create_user_command("LspRestart", function()
  -- Get the current buffer
  local bufnr = vim.api.nvim_get_current_buf()
  local filename = vim.api.nvim_buf_get_name(bufnr)

  -- Get all clients attached to the current buffer
  local clients = vim.lsp.get_clients({ buffer = bufnr })

  if #clients == 0 then
    vim.notify("No LSP clients attached to this buffer", vim.log.levels.WARN)
    return
  end

  -- Store client names to restart
  local client_names = {}
  for _, client in ipairs(clients) do
    table.insert(client_names, client.name)
    local client_name = client.name or "unknown"
    vim.notify("Stopping LSP: " .. client_name, vim.log.levels.INFO)

    -- Stop the client
    vim.lsp.stop_client(client.id, true)
  end

  -- Re-enable clients and re-attach to buffer after a short delay
  vim.defer_fn(function()
    for _, client_name in ipairs(client_names) do
      vim.notify("Restarting LSP: " .. client_name, vim.log.levels.INFO)
      vim.lsp.enable(client_name)
    end

    -- Force LSP to re-attach to the current buffer
    vim.cmd("edit " .. vim.fn.fnameescape(filename))
    vim.notify("LSP clients restarted and re-attached", vim.log.levels.INFO)
  end, 500)
end, { desc = "Restart LSP servers for current buffer" })
