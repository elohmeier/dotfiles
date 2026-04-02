-- Compatibility shim for Neovim < 0.12
if vim.fn.has("nvim-0.12") == 0 then
  vim.pack = {}
  vim.pack.add = function(specs, opts)
    specs = vim.tbl_map(function(s)
      return type(s) == "string" and { src = s } or s
    end, specs)
    opts = vim.tbl_extend("force", { load = vim.v.did_init == 1 }, opts or {})
    local cmd_prefix = "packadd" .. (opts.load and "" or "!")
    for _, s in ipairs(specs) do
      local name = s.name or s.src:match("/([^/]+)$")
      vim.cmd(cmd_prefix .. name)
    end
  end
end

-- Set leaders before loading plugins
vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

-- Install and load mini.nvim
vim.pack.add({ "https://github.com/nvim-mini/mini.nvim" })

-- Loading helpers via mini.misc
local misc = require("mini.misc")
_G.Config = {}
Config.now = function(f)
  misc.safely("now", f)
end
Config.later = function(f)
  misc.safely("later", f)
end
Config.now_if_args = vim.fn.argc(-1) > 0 and Config.now or Config.later

-- Autocommand helpers
local gr = vim.api.nvim_create_augroup("custom-config", {})
Config.new_autocmd = function(event, pattern, callback, desc)
  vim.api.nvim_create_autocmd(event, { group = gr, pattern = pattern, callback = callback, desc = desc })
end
Config.on_packchanged = function(plugin_name, kinds, callback, desc)
  if vim.fn.has("nvim-0.12") == 0 then
    return
  end
  local f = function(ev)
    local name, kind = ev.data.spec.name, ev.data.kind
    if not (name == plugin_name and vim.tbl_contains(kinds, kind)) then
      return
    end
    if not ev.data.active then
      vim.cmd.packadd(plugin_name)
    end
    callback()
  end
  Config.new_autocmd("PackChanged", "*", f, desc)
end

-- Load colorscheme early
Config.now(function()
  require("plugins.colorscheme")
end)

-- Load configuration
Config.now(function()
  require("config.options")
end)
Config.now(function()
  require("config.keymaps")
end)
Config.now(function()
  require("config.autocmds")
end)
Config.now(function()
  require("config.lsp")
end)
Config.now(function()
  require("config.clipboard")
end)
Config.now(function()
  require("config.clipboard-debug")
end)

-- Load plugins
require("plugins")
