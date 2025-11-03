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

vim.lsp.config["ty"] = {
  cmd = { "ty", "server" },
  filetypes = { "python" },
  root_markers = {
    ".git",
    ".ruff.toml",
    "Pipfile",
    "pyproject.toml",
    "requirements.txt",
    "ruff.toml",
    "setup.cfg",
    "setup.py",
    "ty.toml",
  },
  single_file_support = true,
  settings = {
    ty = {
      experimental = {
        autoImport = false,
        rename = true,
      },
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

vim.lsp.config["taplo"] = {
  cmd = { "taplo", "lsp", "stdio" },
  filetypes = { "toml" },
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

vim.lsp.config["yamlls"] = {
  cmd = { "yaml-language-server", "--stdio" },
  filetypes = { "yaml", "yaml.docker-compose", "yaml.gitlab" },
  root_markers = { ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
  settings = {
    yaml = {
      schemas = {
        ["https://json.schemastore.org/github-workflow.json"] = "/.github/workflows/*",
        ["https://json.schemastore.org/docker-compose.json"] = "docker-compose*.yml",
        ["https://raw.githubusercontent.com/compose-spec/compose-spec/master/schema/compose-spec.json"] = "docker-compose*.yml",
      },
      format = {
        enable = true,
      },
      validate = true,
      completion = true,
      hover = true,
    },
  },
}

vim.lsp.config["rust_analyzer"] = {
  cmd = { "rust-analyzer" },
  filetypes = { "rust" },
  root_markers = { "Cargo.toml", "rust-project.json", ".git" },
  single_file_support = true,
  offset_encoding = "utf-8",
  settings = {
    ["rust-analyzer"] = {
      cargo = {
        allFeatures = true,
        loadOutDirsFromCheck = false, -- Disable loading from build scripts
        buildScripts = {
          enable = false, -- Disable build scripts entirely
          invocationStrategy = "once",
          invocationLocation = "workspace",
        },
        extraEnv = {
          CMAKE_POLICY_VERSION_MINIMUM = "3.5", -- Try to help with cmake issues
        },
      },
      procMacro = {
        enable = true,
      },
      checkOnSave = {
        enable = true,
        command = "check", -- Use 'check' instead of 'clippy' for faster builds
        extraArgs = { "--offline" }, -- Work offline to avoid network issues
      },
      diagnostics = {
        disabled = { "unresolved-proc-macro" }, -- Ignore proc macro issues
      },
    },
  },
}

-- Configure LSP logging to reduce log file size
-- Set log level to WARN to only log warnings and errors
vim.lsp.set_log_level("WARN")

-- Helper function to check if command is executable
local function is_executable(cmd)
  if type(cmd) == "table" and #cmd > 0 then
    return vim.fn.executable(cmd[1]) == 1
  elseif type(cmd) == "string" then
    return vim.fn.executable(cmd) == 1
  end
  return false
end

-- Enable LSP servers only if their commands are executable
local servers_to_enable = {
  { name = "basedpyright", config = vim.lsp.config.basedpyright },
  { name = "bashls", config = vim.lsp.config.bashls },
  { name = "helm_ls", config = vim.lsp.config.helm_ls },
  { name = "jsonnet_ls", config = vim.lsp.config.jsonnet_ls },
  { name = "luals", config = vim.lsp.config.luals },
  { name = "ruff_lsp", config = vim.lsp.config.ruff_lsp },
  { name = "rust_analyzer", config = vim.lsp.config.rust_analyzer },
  { name = "svelte", config = vim.lsp.config.svelte },
  { name = "taplo", config = vim.lsp.config.taplo },
  { name = "terraformls", config = vim.lsp.config.terraformls },
  { name = "tinymist", config = vim.lsp.config.tinymist },
  { name = "tsserver", config = vim.lsp.config.tsserver },
  { name = "ty", config = vim.lsp.config.ty },
  { name = "yamlls", config = vim.lsp.config.yamlls },
}

for _, server in ipairs(servers_to_enable) do
  if server.config and is_executable(server.config.cmd) then
    vim.lsp.enable(server.name)
  end
end

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
      vim.api.nvim_create_user_command(cmd_name, cmd_func, { nargs = 0, desc = cmd_desc, force = true })
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
  local bufnr = vim.api.nvim_get_current_buf()
  local clients = vim.lsp.get_clients({ buffer = bufnr })

  if #clients == 0 then
    vim.notify("No LSP clients attached to this buffer", vim.log.levels.WARN)
    return
  end

  local client_names = {}
  for _, client in ipairs(clients) do
    local name = client.name or ("client_" .. client.id)
    client_names[name] = true
    vim.notify("Stopping LSP: " .. name, vim.log.levels.INFO)
    vim.lsp.stop_client(client.id, true)
  end

  vim.defer_fn(function()
    for name in pairs(client_names) do
      vim.notify("Restarting LSP: " .. name, vim.log.levels.INFO)

      local restarted = false
      if vim.lsp and vim.lsp.enable then
        local ok, err = pcall(vim.lsp.enable, name)
        if ok then
          restarted = true
        else
          vim.notify("Failed to restart LSP '" .. name .. "' via vim.lsp.enable: " .. err, vim.log.levels.WARN)
        end
      end

      if not restarted and vim.fn.exists(":LspStart") == 2 then
        local ok, err = pcall(vim.cmd, "LspStart " .. name)
        if ok then
          restarted = true
        else
          vim.notify("Failed to restart LSP '" .. name .. "' via :LspStart: " .. err, vim.log.levels.ERROR)
        end
      end

      if not restarted then
        vim.notify("No restart mechanism available for LSP '" .. name .. "'", vim.log.levels.WARN)
      end
    end
  end, 200)
end, { desc = "Restart LSP servers for current buffer" })
