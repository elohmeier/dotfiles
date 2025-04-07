return {
  "folke/tokyonight.nvim",
  lazy = false,
  priority = 1000,
  opts = {
    style = "day",
  },
  config = function()
    -- Load the colorscheme
    vim.cmd([[colorscheme tokyonight]])
  end,
}
