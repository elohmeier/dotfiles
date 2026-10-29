vim.pack.add({
  { src = "https://github.com/saghen/blink.cmp", version = vim.version.range(">=1.0.0") },
  "https://github.com/rafamadriz/friendly-snippets",
  { src = "https://github.com/kylechui/nvim-surround", version = vim.version.range("4.0") },
  "https://github.com/assistcontrol/readline.nvim",
  "https://github.com/folke/todo-comments.nvim",
  { src = "https://github.com/goerz/jupytext.nvim", version = "v0.2.0" },
  "https://github.com/3rd/image.nvim",
})

require("blink.cmp").setup({})
require("nvim-surround").setup({})
require("todo-comments").setup({})
require("jupytext").setup({}) -- Register notebook read handlers before the first buffer opens.
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

local readline = require("readline")
for lhs, action in pairs({
  ["<M-f>"] = "forward_word",
  ["<M-b>"] = "backward_word",
  ["<C-a>"] = "beginning_of_line",
  ["<C-e>"] = "end_of_line",
  ["<M-d>"] = "kill_word",
  ["<M-BS>"] = "backward_kill_word",
  ["<C-w>"] = "unix_word_rubout",
  ["<C-k>"] = "kill_line",
  ["<C-u>"] = "backward_kill_line",
}) do
  vim.keymap.set("!", lhs, readline[action])
end
