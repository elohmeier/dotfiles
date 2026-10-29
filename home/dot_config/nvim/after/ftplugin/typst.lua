for _, action in ipairs({
  "exportSvg",
  "exportPng",
  "exportPdf",
  "exportMarkdown",
  "exportText",
  "exportQuery",
  "exportAnsiHighlight",
  "getServerInfo",
  "getDocumentTrace",
  "getWorkspaceLabels",
  "getDocumentMetrics",
}) do
  local name = "LspTinymist" .. action:gsub("^%l", string.upper)
  vim.api.nvim_buf_create_user_command(0, name, function()
    local client = vim.lsp.get_clients({ name = "tinymist", bufnr = 0 })[1]
    if not client then
      return vim.notify("No Tinymist client attached", vim.log.levels.WARN)
    end
    client:exec_cmd({
      title = action,
      command = "tinymist." .. action,
      arguments = { vim.api.nvim_buf_get_name(0) },
    }, { bufnr = 0 }, function(err, result)
      if err then
        return vim.notify(err.message, vim.log.levels.ERROR)
      end
      vim.notify(type(result) == "string" and result or vim.inspect(result))
    end)
  end, { desc = "Tinymist: " .. action })
  vim.b.undo_ftplugin = (vim.b.undo_ftplugin or "") .. "\ndelcommand -buffer " .. name
end
