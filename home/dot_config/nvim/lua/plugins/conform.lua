return {
  "stevearc/conform.nvim",
  event = { "BufWritePre" },
  cmd = { "ConformInfo" },
  keys = {
    {
      "<leader>uf",
      "<cmd>FormatToggle<cr>",
      desc = "Toggle Format",
      silent = true,
    },
    {
      "<leader>cf",
      function()
        require("conform").format()
      end,
      desc = "Format Buffer",
      silent = true,
    },
    {
      "<leader>cF",
      function()
        require("conform").format()
      end,
      mode = "v",
      desc = "Format Lines",
      silent = true,
    },
  },
  opts = {
    formatters_by_ft = {
      astro = { "dprint" },
      bash = { "shfmt" },
      cpp = { "clang-format" },
      css = { "dprint" },
      hcl = { "packer_fmt" },
      html = { "dprint" },
      htmldjango = { "djade" },
      javascript = { "dprint" },
      json = { "dprint" },
      just = { "just" },
      jsonnet = { "jsonnetfmt" },
      lua = { "stylua" },
      markdown = { "rumdl" },
      nix = { "nixfmt" },
      python = { "ruff_format", "ruff_fix" },
      sh = { "shfmt" },
      svelte = { "dprint" },
      terraform = { "tofu_fmt" },
      toml = { "taplo" },
      typescript = { "dprint" },
      typst = { "typstyle" },
      xml = { "xmllint" },
      yaml = { "dprint" },
      zsh = { "shfmt" },
      ["_"] = { "trim_whitespace" },
    },
    formatters = {
      dprint = {
        prepend_args = function()
          -- Check if dprint.json exists in cwd or parent directories
          local cwd = vim.fn.getcwd()
          local config_path = vim.fn.findfile("dprint.json", cwd .. ";")

          -- If no local config found, use global config
          if config_path == "" then
            local global_config = vim.fn.expand("~/.config/dprint.json")
            if vim.fn.filereadable(global_config) == 1 then
              return { "--config", global_config }
            end
          end

          return {}
        end,
      },
      djade = {
        meta = {
          url = "https://github.com/adamchainz/djade",
          description = "A Django template formatter.",
        },
        command = "djade",
        args = { "$FILENAME" },
        stdin = false,
        exit_codes = { 0, 1 },
      },
      ruff_fix = {
        args = {
          "check",
          "--fix",
          "--select",
          "I,UP",
          "--force-exclude",
          "--exit-zero",
          "--no-cache",
          "--stdin-filename",
          "$FILENAME",
          "-",
        },
      },
      rumdl = {
        command = "rumdl",
        args = {
          "fmt",
          "-",
          "--stdin-filename",
          "$FILENAME",
          "-d",
          "MD013", -- ignore line length
        },
        stdin = true,
      },
      shfmt = {
        prepend_args = { "-i", "4" },
      },
      taplo = {
        command = "taplo",
        args = { "format", "--stdin-filepath", "$FILENAME", "-" },
      },
    },
    format_on_save = function(bufnr)
      -- Disable with a global or buffer-local variable
      if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat then
        return
      end
      return { timeout_ms = 1500, lsp_fallback = true }
    end,
  },
  init = function()
    -- Create user commands for toggling format-on-save
    local notify_ok, notify = pcall(require, "notify")

    local function show_notification(message, level)
      if notify_ok then
        notify(message, level, { title = "conform.nvim" })
      else
        vim.notify(message, vim.log.levels[level:upper()])
      end
    end

    vim.api.nvim_create_user_command("FormatToggle", function(args)
      local is_global = not args.bang
      if is_global then
        vim.g.disable_autoformat = not vim.g.disable_autoformat
        if vim.g.disable_autoformat then
          show_notification("Autoformat-on-save disabled globally", "info")
        else
          show_notification("Autoformat-on-save enabled globally", "info")
        end
      else
        vim.b.disable_autoformat = not vim.b.disable_autoformat
        if vim.b.disable_autoformat then
          show_notification("Autoformat-on-save disabled for this buffer", "info")
        else
          show_notification("Autoformat-on-save enabled for this buffer", "info")
        end
      end
    end, {
      desc = "Toggle autoformat-on-save",
      bang = true,
    })

    vim.api.nvim_create_user_command("RuffFix", function()
      if vim.bo.filetype == "python" then
        require("conform").format({ bufnr = 0, formatters = { "ruff_fix" } })
      else
        show_notification("RuffFix is only available for Python files", "warn")
      end
    end, {
      desc = "Run ruff_fix formatter on Python files",
    })
  end,
}
