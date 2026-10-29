local group = vim.api.nvim_create_augroup("config.pack", { clear = true })
local hooks = {
  ["nvim-treesitter"] = function()
    require("nvim-treesitter").update()
  end,
  ["fff.nvim"] = function()
    require("fff.download").download_binary()
  end,
}

vim.api.nvim_create_autocmd("PackChanged", {
  group = group,
  callback = function(ev)
    local name, kind = ev.data.spec.name, ev.data.kind
    if hooks[name] and (kind == "install" or kind == "update") then
      if not ev.data.active then
        vim.cmd.packadd(name)
      end
      hooks[name]()
    end
  end,
})

-- Parser definitions are reloaded on every Treesitter update.
vim.api.nvim_create_autocmd("User", {
  group = group,
  pattern = "TSUpdate",
  callback = function()
    require("nvim-treesitter.parsers").rhai = {
      install_info = {
        url = "https://github.com/elkowar/tree-sitter-rhai",
        revision = "4ac7384d487ffcb54e746ef1569585a749370c5b",
      },
    }
  end,
})
