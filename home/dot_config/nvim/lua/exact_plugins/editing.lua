vim.pack.add({
  { src = "https://github.com/kylechui/nvim-surround", version = vim.version.range("4.0") },
  { src = "https://github.com/goerz/jupytext.nvim", version = "v0.2.0" },
  "https://github.com/3rd/image.nvim",
})

require("nvim-surround").setup({})
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
