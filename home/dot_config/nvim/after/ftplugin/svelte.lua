vim.api.nvim_buf_create_user_command(0, "MigrateToSvelte5", function()
  local client = vim.lsp.get_clients({ name = "svelte", bufnr = 0 })[1]
  if not client then
    return vim.notify("No Svelte language server attached", vim.log.levels.WARN)
  end
  client:exec_cmd({ command = "migrate_to_svelte_5", arguments = { vim.uri_from_bufnr(0) } }, { bufnr = 0 })
end, { desc = "Migrate Component to Svelte 5 Syntax" })
vim.b.undo_ftplugin = (vim.b.undo_ftplugin or "") .. "\ndelcommand -buffer MigrateToSvelte5"
