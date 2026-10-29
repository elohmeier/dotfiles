vim.pack.add({
  "https://github.com/nvim-tree/nvim-web-devicons",
  "https://github.com/nvim-lua/plenary.nvim",
  "https://github.com/MunifTanjim/nui.nvim",
  "https://github.com/nvim-neo-tree/neo-tree.nvim",
  "https://github.com/nvim-telescope/telescope.nvim",
  "https://github.com/dmtrKovalenko/fff.nvim",
})

require("nvim-web-devicons").setup()

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

local function root()
  return vim.fs.root(0, ".git") or vim.fn.getcwd()
end

local function explorer(lhs, source, dir, desc)
  vim.keymap.set("n", lhs, function()
    require("neo-tree.command").execute({ action = "focus", source = source, position = "left", dir = dir and dir() })
  end, { desc = desc })
end
explorer("<leader>fe", "filesystem", vim.fn.getcwd, "Files (cwd)")
explorer("<leader>fE", "filesystem", root, "Files (git root)")
explorer("<leader>f.", "filesystem", function()
  return vim.fn.expand("%:p:h")
end, "Files (current directory)")
explorer("<leader>ge", "git_status", nil, "Git Explorer")
explorer("<leader>be", "buffers", nil, "Buffer Explorer")
explorer("<leader>se", "document_symbols", nil, "Document Symbols Explorer")

local telescope = require("telescope")
local actions = require("telescope.actions")

telescope.setup({
  defaults = {
    mappings = { i = { ["<esc>"] = actions.close } },
    file_ignore_patterns = { "%.direnv/.*" },
  },
})

vim.cmd.packadd("nvim.undotree")
vim.keymap.set("n", "<leader>su", "<cmd>Undotree<cr>", { desc = "Undo Tree" })

vim.keymap.set("n", "<leader>/", function()
  require("telescope.builtin").live_grep({ cwd = root() })
end, { desc = "Grep (git root)" })
vim.keymap.set("n", "<leader>:", "<cmd>Telescope command_history<cr>", { desc = "Command History" })
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
vim.keymap.set("n", "<leader>st", function()
  require("telescope.builtin").grep_string({
    cwd = root(),
    prompt_title = "TODO comments",
    search = [[\b(FIX|FIXME|BUG|FIXIT|ISSUE|TODO|HACK|WARN|WARNING|XXX|PERF|OPTIM|PERFORMANCE|OPTIMIZE|NOTE|INFO|TEST|TESTING|PASSED|FAILED):]],
    use_regex = true,
  })
end, { desc = "Todo (Telescope)" })

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

local find_files = require("fff").find_files
vim.keymap.set("n", "<C-p>", find_files, { desc = "Find Project Files" })
vim.keymap.set("n", "<leader>ff", find_files, { desc = "Find Project Files" })
