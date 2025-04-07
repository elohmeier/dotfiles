return {
  "nvim-neo-tree/neo-tree.nvim",
  branch = "v3.x",
  dependencies = {
    "nvim-lua/plenary.nvim",
    "nvim-tree/nvim-web-devicons",
    "MunifTanjim/nui.nvim",
  },
  lazy = false,
  opts = {
    sources = { "filesystem", "buffers", "git_status", "document_symbols" },
    filesystem = {
      bind_to_cwd = false,
      follow_current_file = { enabled = true },
      use_libuv_file_watcher = true,
      filtered_items = {
        hide_by_name = {
          ".git",
          ".DS_Store",
          ".direnv",
          ".ipynb_checkpoints",
          ".pytest_cache",
          ".ruff_cache",
          ".terraform",
          "__pycache__",
          "dump.rdb",
          "node_modules",
        },
        hide_by_pattern = {
          "*.aider*",
        },
        hide_gitignored = false,
        hide_dotfiles = false,
      },
    },
    default_component_configs = {
      -- ASCII mode configuration
      -- Uncomment the following if you want to use ASCII mode
      -- icon = {
      --   folder_closed = "▸",
      --   folder_open = "▾",
      --   folder_empty = "▸",
      --   folder_empty_open = "▾",
      -- },
      symlink_target = {
        enabled = true,
      },
    },
  },
  keys = {
    {
      "<leader>fe",
      function()
        require("neo-tree.command").execute({
          action = "focus",
          source = "filesystem",
          position = "left",
          dir = vim.loop.cwd(),
        })
      end,
      desc = "Neo-tree file explorer (cwd)",
    },
    {
      "<leader>fE",
      function()
        local git_utils = require("neo-tree.git.utils")
        require("neo-tree.command").execute({
          action = "focus",
          source = "filesystem",
          position = "left",
          dir = git_utils.get_repository_root(),
        })
      end,
      desc = "Neo-tree file explorer (git repo root)",
    },
    {
      "<leader>f.",
      function()
        require("neo-tree.command").execute({
          action = "focus",
          source = "filesystem",
          position = "left",
          dir = vim.fn.expand("%:p:h"),
        })
      end,
      desc = "Neo-tree file explorer (current file parent)",
    },
    {
      "<leader>ge",
      function()
        require("neo-tree.command").execute({ action = "focus", source = "git_status", position = "left" })
      end,
      desc = "Neo-tree git explorer",
    },
    {
      "<leader>be",
      function()
        require("neo-tree.command").execute({ action = "focus", source = "buffers", position = "left" })
      end,
      desc = "Neo-tree buffer explorer",
    },
    {
      "<leader>de",
      function()
        require("neo-tree.command").execute({ action = "focus", source = "document_symbols", position = "left" })
      end,
      desc = "Neo-tree document symbols explorer",
    },
  },
}
