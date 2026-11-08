vim.pack.add({
  { src = "https://github.com/kylechui/nvim-surround", version = vim.version.range("4.0") },
})

require("nvim-surround").setup({})

if vim.fn.executable("jupytext") == 1 then
  vim.pack.add({ { src = "https://github.com/goerz/jupytext.nvim", version = "v0.2.0" } })
  require("jupytext").setup({}) -- Register notebook read handlers before the first buffer opens.
end

if vim.fn.executable("magick") == 1 then
  vim.pack.add({ "https://github.com/3rd/image.nvim" })
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
end
