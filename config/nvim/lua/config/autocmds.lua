-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")

-- Automatically set filetype to 'helm' if Chart.yaml is found in a parent directory
vim.api.nvim_create_autocmd("BufReadPost", {
  group = vim.api.nvim_create_augroup("helm_filetype", { clear = true }),
  pattern = "*", -- Apply to all files
  callback = function()
    local bufnr = vim.api.nvim_get_current_buf()
    local filename = vim.api.nvim_buf_get_name(bufnr)

    -- Skip if the buffer is not associated with a file
    if filename == "" or vim.fn.empty(filename) == 1 then
      return
    end

    -- Find Chart.yaml in the current directory or any parent directory
    local chart_yaml_path = vim.fn.findfile("Chart.yaml", vim.fn.expand("%:h") .. ";", -1)

    -- If Chart.yaml is found, set the filetype to helm
    if chart_yaml_path ~= "" then
      vim.bo[bufnr].filetype = "helm"
    end
  end,
})
