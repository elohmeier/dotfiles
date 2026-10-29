vim.pack.add({ "https://github.com/stevearc/resession.nvim" })
local resession = require("resession")
resession.setup({
  autosave = { enabled = true, notify = false },
  options = { "binary", "bufhidden", "buflisted", "filetype", "modifiable", "readonly" },
  buf_filter = function(bufnr)
    return vim.bo[bufnr].buflisted and vim.tbl_contains({ "", "acwrite" }, vim.bo[bufnr].buftype)
  end,
})
vim.api.nvim_create_autocmd("VimLeavePre", {
  group = vim.api.nvim_create_augroup("config.sessions", { clear = true }),
  callback = function()
    resession.save("last", { notify = false })
  end,
})
vim.keymap.set("n", "<leader>Ss", resession.save, { desc = "Save Session" })
vim.keymap.set("n", "<leader>Sl", resession.load, { desc = "Load Session" })
vim.keymap.set("n", "<leader>Sd", resession.delete, { desc = "Delete Session" })
