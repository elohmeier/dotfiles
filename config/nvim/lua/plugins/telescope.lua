return {
  "nvim-telescope/telescope.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
    { "nvim-telescope/telescope-frecency.nvim", version = "*" },
    "nvim-telescope/telescope-ui-select.nvim",
    "debugloop/telescope-undo.nvim",
  },
  config = function()
    local telescope = require("telescope")
    local actions = require("telescope.actions")

    telescope.setup({
      defaults = {
        mappings = {
          i = {
            -- Close Telescope prompt on Escape in insert mode
            ["<esc>"] = actions.close,
          },
        },
      },
      extensions = {
        frecency = {
          db_safe_mode = false, -- disable "remove n entries from database?" dialog
          matcher = "fuzzy",
        },
        ["ui-select"] = {},
        undo = {},
      },
    })

    telescope.load_extension("frecency")
    telescope.load_extension("ui-select")
    telescope.load_extension("undo")

    -- Keymaps
    vim.keymap.set(
      "n",
      "<C-p>",
      "<cmd>Telescope frecency workspace=CWD<cr>",
      { desc = "Find frequent or recent files" }
    )
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

    -- Additional keymaps from the keymaps section
    vim.keymap.set("n", "<leader>fs", "<cmd>Telescope lsp_document_symbols<cr>", { desc = "Document symbols" })
    vim.keymap.set("n", "<C-j>", "<cmd>Telescope lsp_references<cr>", { desc = "References" })
    vim.keymap.set("n", "<leader>sd", "<cmd>Telescope diagnostics bufnr=0<cr>", { desc = "Document diagnostics" })
    vim.keymap.set("n", "<leader>st", "<cmd>TodoTelescope<cr>", { silent = true, desc = "Todo (Telescope)" })
  end,
}
