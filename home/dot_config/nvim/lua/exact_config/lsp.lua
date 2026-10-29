vim.lsp.enable({
  vim.env.NVIM_PYTHON_LSP or "ty",
  "bashls",
  "helm_ls",
  "jsonnet_ls",
  "luals",
  "ruff_lsp",
  "ruby_lsp",
  "rust_analyzer",
  "svelte",
  "taplo",
  "terraformls",
  "tinymist",
  "tsserver",
  "yamlls",
})

vim.diagnostic.config({ virtual_lines = { current_line = true } })

local group = vim.api.nvim_create_augroup("config.lsp", { clear = true })
vim.api.nvim_create_autocmd("LspAttach", {
  group = group,
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client:supports_method("textDocument/completion") then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end
  end,
})
vim.api.nvim_create_autocmd({ "CursorHold", "CursorHoldI" }, {
  group = group,
  callback = function(ev)
    if #vim.lsp.get_clients({ bufnr = ev.buf, method = "textDocument/documentHighlight" }) > 0 then
      vim.lsp.buf.document_highlight()
    end
  end,
})
vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI", "LspDetach" }, {
  group = group,
  callback = vim.lsp.buf.clear_references,
})

vim.keymap.set("n", "<leader>vrn", vim.lsp.buf.rename, { desc = "Rename" })
vim.keymap.set("n", "<leader>e", vim.diagnostic.open_float, { desc = "Show Diagnostic" })
vim.keymap.set("n", "<C-k>", vim.lsp.buf.definition, { desc = "Goto Definition" })
for lhs, direction in pairs({ ["]d"] = 1, ["[d"] = -1 }) do
  vim.keymap.set("n", lhs, function()
    vim.diagnostic.jump({
      count = direction * vim.v.count1,
      severity = { min = vim.diagnostic.severity.WARN },
      float = false,
    })
  end, { desc = direction == 1 and "Next Diagnostic" or "Previous Diagnostic" })
end
