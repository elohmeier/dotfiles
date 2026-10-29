vim.api.nvim_buf_create_user_command(0, "RuffFix", function()
  require("conform").format({ formatters = { "ruff_fix" } })
end, { desc = "Apply Ruff import sorting and modernization fixes" })
vim.b.undo_ftplugin = (vim.b.undo_ftplugin or "") .. "\ndelcommand -buffer RuffFix"
