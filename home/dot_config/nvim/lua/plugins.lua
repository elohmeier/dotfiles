local add = vim.pack.add

-- Build hooks (must be registered before vim.pack.add calls)
Config.on_packchanged("nvim-treesitter", { "install", "update" }, function()
  require("nvim-treesitter").update()
end, ":TSUpdate")

Config.on_packchanged("fff.nvim", { "install", "update" }, function()
  require("fff.download").download_binary()
end, "Download fff.nvim binary")

-- ==========================================================================
-- Immediate loading
-- ==========================================================================

Config.now(function()
  add({ "https://github.com/nvim-tree/nvim-web-devicons" })
  require("nvim-web-devicons").setup()
end)

Config.now(function()
  add({ "https://github.com/nvim-lualine/lualine.nvim" })
  require("lualine").setup({ options = { theme = "auto" } })
end)

Config.now(function()
  add({
    "https://github.com/nvim-neo-tree/neo-tree.nvim",
    "https://github.com/nvim-lua/plenary.nvim",
    "https://github.com/MunifTanjim/nui.nvim",
  })
  require("neo-tree").setup({
    sources = { "filesystem", "buffers", "git_status", "document_symbols" },
    filesystem = {
      bind_to_cwd = false,
      follow_current_file = { enabled = true },
      use_libuv_file_watcher = true,
      filtered_items = {
        hide_by_name = {
          "__pycache__",
          "dprint.json",
          "dump.rdb",
          "node_modules",
          "uv.lock",
          "vendor",
        },
        hide_by_pattern = { "*.dvc" },
        hide_gitignored = false,
        hide_dotfiles = true,
      },
    },
    default_component_configs = {
      symlink_target = { enabled = true },
    },
  })

  vim.keymap.set("n", "<leader>fe", function()
    require("neo-tree.command").execute({
      action = "focus",
      source = "filesystem",
      position = "left",
      dir = vim.loop.cwd(),
    })
  end, { desc = "Neo-tree file explorer (cwd)" })
  vim.keymap.set("n", "<leader>fE", function()
    require("neo-tree.command").execute({
      action = "focus",
      source = "filesystem",
      position = "left",
      dir = require("neo-tree.git.utils").get_repository_root(),
    })
  end, { desc = "Neo-tree file explorer (git repo root)" })
  vim.keymap.set("n", "<leader>f.", function()
    require("neo-tree.command").execute({
      action = "focus",
      source = "filesystem",
      position = "left",
      dir = vim.fn.expand("%:p:h"),
    })
  end, { desc = "Neo-tree file explorer (current file parent)" })
  vim.keymap.set("n", "<leader>ge", function()
    require("neo-tree.command").execute({ action = "focus", source = "git_status", position = "left" })
  end, { desc = "Neo-tree git explorer" })
  vim.keymap.set("n", "<leader>be", function()
    require("neo-tree.command").execute({ action = "focus", source = "buffers", position = "left" })
  end, { desc = "Neo-tree buffer explorer" })
  vim.keymap.set("n", "<leader>de", function()
    require("neo-tree.command").execute({ action = "focus", source = "document_symbols", position = "left" })
  end, { desc = "Neo-tree document symbols explorer" })
end)

-- ==========================================================================
-- Treesitter (immediate if files passed, deferred otherwise)
-- ==========================================================================

Config.now_if_args(function()
  add({
    "https://github.com/nvim-treesitter/nvim-treesitter",
  })

  local langs = {
    "bash",
    "beancount",
    "c",
    "git_config",
    "git_rebase",
    "gitattributes",
    "gitcommit",
    "gitignore",
    "hcl",
    "helm",
    "javascript",
    "jsdoc",
    "json",
    "jsonnet",
    "just",
    "lua",
    "make",
    "markdown",
    "nix",
    "puppet",
    "python",
    "readline",
    "regex",
    "ruby",
    "rust",
    "svelte",
    "terraform",
    "toml",
    "typescript",
    "typst",
    "vim",
    "vimdoc",
    "xml",
    "yaml",
  }

  local installed = require("nvim-treesitter.config").get_installed("parsers")
  local missing = vim.tbl_filter(function(l)
    return not vim.tbl_contains(installed, l)
  end, langs)
  if #missing > 0 then
    require("nvim-treesitter").install(missing)
  end

  local no_indent = { yaml = true }
  vim.api.nvim_create_autocmd("FileType", {
    callback = function(ev)
      local ft = vim.bo[ev.buf].filetype
      local lang = vim.treesitter.language.get_lang(ft)
      if not lang then
        return
      end
      if not pcall(vim.treesitter.start, ev.buf, lang) then
        return
      end
      if not no_indent[ft] then
        vim.bo[ev.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
      end
    end,
  })
end)

Config.later(function()
  add({ "https://github.com/nvim-treesitter/nvim-treesitter-context" })
  require("treesitter-context").setup({
    enable = true,
    max_lines = 0,
    min_window_height = 0,
    line_numbers = true,
    multiline_threshold = 20,
    trim_scope = "outer",
    mode = "cursor",
    separator = nil,
    zindex = 20,
    on_attach = nil,
  })
  vim.keymap.set("n", "<leader>tc", function()
    require("treesitter-context").toggle()
  end, { desc = "Toggle Treesitter Context" })
end)

-- ==========================================================================
-- Deferred loading
-- ==========================================================================

Config.later(function()
  add({
    { src = "https://github.com/saghen/blink.cmp", version = vim.version.range(">=1.0.0") },
    "https://github.com/rafamadriz/friendly-snippets",
  })
  require("blink.cmp").setup({
    keymap = { preset = "default" },
    appearance = { nerd_font_variant = "mono" },
    completion = { documentation = { auto_show = false } },
    sources = { default = { "lsp", "path", "snippets", "buffer" } },
    fuzzy = { implementation = "prefer_rust_with_warning" },
  })
end)

Config.later(function()
  add({
    "https://github.com/nvim-telescope/telescope.nvim",
    "https://github.com/nvim-telescope/telescope-ui-select.nvim",
    "https://github.com/debugloop/telescope-undo.nvim",
  })
  local telescope = require("telescope")
  local actions = require("telescope.actions")

  telescope.setup({
    defaults = {
      mappings = { i = { ["<esc>"] = actions.close } },
      file_ignore_patterns = { "%.direnv/.*" },
    },
    extensions = { ["ui-select"] = {}, undo = {} },
  })

  telescope.load_extension("ui-select")
  telescope.load_extension("undo")

  vim.keymap.set("n", "<leader>/", "<cmd>Telescope live_grep<cr>", { desc = "Grep (root dir)" })
  vim.keymap.set("n", "<leader>:", "<cmd>Telescope command_history<cr>", { desc = "Command History" })
  vim.keymap.set("n", "<leader>b", "<cmd>Telescope buffers<cr>", { desc = "+buffer" })
  vim.keymap.set("n", "<leader>fr", "<cmd>Telescope oldfiles<cr>", { desc = "Recent" })
  vim.keymap.set("n", "<leader>fb", "<cmd>Telescope buffers<cr>", { desc = "Buffers" })
  vim.keymap.set("n", "<leader>fg", "<cmd>Telescope git_files<cr>", { desc = "Search git files" })
  vim.keymap.set("n", "<leader>gc", "<cmd>Telescope git_commits<cr>", { desc = "Commits" })
  vim.keymap.set("n", "<leader>gs", "<cmd>Telescope git_status<cr>", { desc = "Status" })
  vim.keymap.set("n", "<leader>sa", "<cmd>Telescope autocommands<cr>", { desc = "Auto Commands" })
  vim.keymap.set("n", "<leader>sb", "<cmd>Telescope current_buffer_fuzzy_find<cr>", { desc = "Buffer" })
  vim.keymap.set("n", "<leader>sc", "<cmd>Telescope command_history<cr>", { desc = "Command History" })
  vim.keymap.set("n", "<leader>sC", "<cmd>Telescope commands<cr>", { desc = "Commands" })
  vim.keymap.set("n", "<leader>sD", "<cmd>Telescope diagnostics<cr>", { desc = "Workspace diagnostics" })
  vim.keymap.set("n", "<leader>sh", "<cmd>Telescope help_tags<cr>", { desc = "Help pages" })
  vim.keymap.set("n", "<leader>sH", "<cmd>Telescope highlights<cr>", { desc = "Search Highlight Groups" })
  vim.keymap.set("n", "<leader>sk", "<cmd>Telescope keymaps<cr>", { desc = "Keymaps" })
  vim.keymap.set("n", "<leader>sM", "<cmd>Telescope man_pages<cr>", { desc = "Man pages" })
  vim.keymap.set("n", "<leader>sm", "<cmd>Telescope marks<cr>", { desc = "Jump to Mark" })
  vim.keymap.set("n", "<leader>so", "<cmd>Telescope vim_options<cr>", { desc = "Options" })
  vim.keymap.set("n", "<leader>sR", "<cmd>Telescope resume<cr>", { desc = "Resume" })
  vim.keymap.set("n", "<leader>fs", "<cmd>Telescope lsp_document_symbols<cr>", { desc = "Document symbols" })
  vim.keymap.set("n", "<C-j>", "<cmd>Telescope lsp_references<cr>", { desc = "References" })
  vim.keymap.set("n", "<leader>sd", "<cmd>Telescope diagnostics bufnr=0<cr>", { desc = "Document diagnostics" })
  vim.keymap.set("n", "<leader>st", "<cmd>TodoTelescope<cr>", { silent = true, desc = "Todo (Telescope)" })

  vim.keymap.set("n", "<leader>ft", function()
    require("telescope.builtin").find_files({
      prompt_title = "Templates",
      cwd = vim.fn.stdpath("config") .. "/templates",
      attach_mappings = function(_, map)
        map("i", "<CR>", function(prompt_bufnr)
          local selection = require("telescope.actions.state").get_selected_entry()
          require("telescope.actions").close(prompt_bufnr)
          if selection then
            local content = vim.fn.readfile(selection.path)
            local cursor = vim.api.nvim_win_get_cursor(0)
            local line = cursor[1]
            vim.api.nvim_buf_set_lines(0, line - 1, line - 1, false, content)
            vim.api.nvim_win_set_cursor(0, { line + #content - 1, 0 })
          end
        end)
        return true
      end,
    })
  end, { desc = "Insert Template" })
end)

Config.later(function()
  add({ "https://github.com/lewis6991/gitsigns.nvim" })
  require("gitsigns").setup({
    current_line_blame = false,
    on_attach = function(bufnr)
      if vim.api.nvim_buf_get_name(bufnr):match("%.ipynb$") then
        return false
      end
    end,
  })
  vim.keymap.set("n", "<leader>gh", "", { desc = "+hunks" })
  vim.keymap.set("n", "<leader>ghb", ":Gitsigns blame_line<CR>", { desc = "Blame line", silent = true })
  vim.keymap.set("n", "<leader>ghd", ":Gitsigns diffthis<CR>", { desc = "Diff This", silent = true })
  vim.keymap.set("n", "<leader>ghp", ":Gitsigns preview_hunk<CR>", { desc = "Preview hunk", silent = true })
  vim.keymap.set("n", "<leader>ghR", ":Gitsigns reset_buffer<CR>", { desc = "Reset Buffer", silent = true })
  vim.keymap.set({ "n", "v" }, "<leader>ghr", ":Gitsigns reset_hunk<CR>", { desc = "Reset Hunk", silent = true })
  vim.keymap.set({ "n", "v" }, "<leader>ghs", ":Gitsigns stage_hunk<CR>", { desc = "Stage Hunk", silent = true })
  vim.keymap.set("n", "<leader>ghS", ":Gitsigns stage_buffer<CR>", { desc = "Stage Buffer", silent = true })
  vim.keymap.set("n", "<leader>ghu", ":Gitsigns undo_stage_hunk<CR>", { desc = "Undo Stage Hunk", silent = true })
end)

Config.later(function()
  add({ "https://github.com/stevearc/conform.nvim" })
  require("conform").setup({
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
      puppet = { "puppet_fmt" },
      python = { "ruff_format", "ruff_fix" },
      ruby = { "rubocop" },
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
          local cwd = vim.fn.getcwd()
          local config_path = vim.fn.findfile("dprint.json", cwd .. ";")
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
        meta = { url = "https://github.com/adamchainz/djade", description = "A Django template formatter." },
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
        args = { "fmt", "-", "--stdin-filename", "$FILENAME", "-d", "MD013" },
        stdin = true,
      },
      puppet_fmt = {
        command = "puppet-fmt",
        args = { "--indentation", "2", "--no-spacing" },
        stdin = true,
      },
      shfmt = { prepend_args = { "-i", "4" } },
      taplo = {
        command = "taplo",
        args = { "format", "--stdin-filepath", "$FILENAME", "-" },
      },
    },
    format_on_save = function(bufnr)
      if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat then
        return
      end
      return { timeout_ms = 1500, lsp_fallback = true }
    end,
  })

  local function show_notification(message, level)
    local notify_ok, notify = pcall(require, "notify")
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
      show_notification(
        vim.g.disable_autoformat and "Autoformat-on-save disabled globally" or "Autoformat-on-save enabled globally",
        "info"
      )
    else
      vim.b.disable_autoformat = not vim.b.disable_autoformat
      show_notification(
        vim.b.disable_autoformat and "Autoformat-on-save disabled for this buffer"
          or "Autoformat-on-save enabled for this buffer",
        "info"
      )
    end
  end, { desc = "Toggle autoformat-on-save", bang = true })

  vim.api.nvim_create_user_command("RuffFix", function()
    if vim.bo.filetype == "python" then
      require("conform").format({ bufnr = 0, formatters = { "ruff_fix" } })
    else
      show_notification("RuffFix is only available for Python files", "warn")
    end
  end, { desc = "Run ruff_fix formatter on Python files" })

  vim.keymap.set("n", "<leader>uf", "<cmd>FormatToggle<cr>", { desc = "Toggle Format", silent = true })
  vim.keymap.set("n", "<leader>cf", function()
    require("conform").format()
  end, { desc = "Format Buffer", silent = true })
  vim.keymap.set("v", "<leader>cF", function()
    require("conform").format()
  end, { desc = "Format Lines", silent = true })
end)

Config.later(function()
  add({ { src = "https://github.com/kylechui/nvim-surround", version = vim.version.range("4.0") } })
  require("nvim-surround").setup({})
end)

Config.later(function()
  add({ "https://github.com/assistcontrol/readline.nvim" })
  local readline = require("readline")
  vim.keymap.set("!", "<M-f>", readline.forward_word)
  vim.keymap.set("!", "<M-b>", readline.backward_word)
  vim.keymap.set("!", "<C-a>", readline.beginning_of_line)
  vim.keymap.set("!", "<C-e>", readline.end_of_line)
  vim.keymap.set("!", "<M-d>", readline.kill_word)
  vim.keymap.set("!", "<M-BS>", readline.backward_kill_word)
  vim.keymap.set("!", "<C-w>", readline.unix_word_rubout)
  vim.keymap.set("!", "<C-k>", readline.kill_line)
  vim.keymap.set("!", "<C-u>", readline.backward_kill_line)
end)

Config.later(function()
  add({
    "https://github.com/folke/todo-comments.nvim",
  })
  require("todo-comments").setup({})
end)

Config.later(function()
  add({ "https://github.com/kdheepak/lazygit.nvim" })
  vim.keymap.set("n", "<leader>gg", "<cmd>LazyGit<CR>", { desc = "Open LazyGit" })
end)

Config.later(function()
  add({ "https://github.com/stevearc/resession.nvim" })
  local resession = require("resession")
  resession.setup({
    autosave = { enabled = true, notify = false },
    options = { "binary", "bufhidden", "buflisted", "filetype", "modifiable", "readonly" },
    extensions = {},
    buf_filter = function(bufnr)
      local buftype = vim.bo[bufnr].buftype
      local filetype = vim.bo[bufnr].filetype
      if buftype ~= "" and buftype ~= "acwrite" then
        return false
      end
      if
        filetype == "neo-tree"
        or filetype == "neo-tree-popup"
        or filetype == "TelescopePrompt"
        or filetype == "lazy"
        or filetype == "toggleterm"
        or filetype == "help"
      then
        return false
      end
      return true
    end,
  })
  vim.api.nvim_create_autocmd("VimLeavePre", {
    callback = function()
      resession.save("last")
    end,
  })
  vim.keymap.set("n", "<leader>ss", function()
    resession.save()
  end, { desc = "Save Session", silent = true })
  vim.keymap.set("n", "<leader>sl", function()
    resession.load()
  end, { desc = "Load Session", silent = true })
  vim.keymap.set("n", "<leader>sd", function()
    resession.delete()
  end, { desc = "Delete Session", silent = true })
end)

Config.later(function()
  add({ "https://github.com/julienvincent/hunk.nvim" })
  require("hunk").setup()
end)

Config.later(function()
  add({ "https://github.com/rafikdraoui/jj-diffconflicts" })
end)

Config.later(function()
  add({ { src = "https://github.com/goerz/jupytext.nvim", version = "v0.2.0" } })
  require("jupytext").setup({})
end)

Config.later(function()
  add({ "https://github.com/3rd/image.nvim" })
  require("image").setup({
    backend = "kitty",
    integrations = {
      markdown = { enabled = true },
      neorg = { enabled = false },
      typst = { enabled = false },
    },
    max_width = 100,
    max_height = 12,
    max_height_window_percentage = math.huge,
    max_width_window_percentage = math.huge,
    window_overlap_clear_enabled = false,
  })
end)

Config.later(function()
  vim.g.fff = { lazy_sync = true }
  add({ "https://github.com/dmtrKovalenko/fff.nvim" })
  require("fff.download").ensure_downloaded({}, function(ok)
    if ok then
      vim.schedule(function()
        require("fff").setup({})
        require("fff.core").ensure_initialized()
      end)
    end
  end)
  vim.keymap.set("n", "<C-p>", function()
    require("fff").find_files()
  end, { desc = "Find files in current directory" })
  vim.keymap.set("n", "<leader>ff", function()
    require("fff").find_files()
  end, { desc = "Find project files" })
end)
