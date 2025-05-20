-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")

-- Automatically set filetype to 'helm' for YAML files if Chart.yaml is found in its directory or near parent directories (up to 2 levels up)
vim.api.nvim_create_autocmd("BufReadPost", {
  group = vim.api.nvim_create_augroup("helm_filetype", { clear = true }),
  pattern = "*.yaml,*.yml,*.tpl", -- Trigger for YAML files and Helm template files
  callback = function(args)
    local bufnr = args.buf -- Use bufnr from autocommand arguments
    local filename = vim.api.nvim_buf_get_name(bufnr)

    -- Skip if the buffer is not associated with a file (though pattern should mostly handle this)
    if filename == "" or vim.fn.empty(filename) == 1 then
      return
    end

    -- For .tpl files, we want to set them as helm regardless of current filetype
    local is_tpl = filename:match("%.tpl$")

    -- For YAML files, explicitly check if the filetype is already 'yaml'
    -- This ensures we only proceed if Neovim's initial detection identified it as YAML
    if not is_tpl and vim.bo[bufnr].filetype ~= "yaml" then
      return
    end

    -- Get the directory of the current buffer.
    -- vim.fn.expand("#" .. bufnr .. ":h") correctly gets the directory path.
    -- If the file is in the current working directory and opened with a relative path, this might return ".".
    local dir_of_file = vim.fn.expand("#" .. bufnr .. ":h")

    -- If dir_of_file is empty (e.g., for a buffer not tied to a file), exit.
    -- This should be rare for BufReadPost with a file pattern.
    if dir_of_file == "" then
      return
    end

    -- Find Chart.yaml in the current file's directory or up to 2 parent directories.
    -- The path for findfile needs a trailing ';' to indicate upward search.
    -- The third argument `-3` limits the search to 3 levels:
    -- current directory, parent directory, and grandparent directory.
    local chart_yaml_path = vim.fn.findfile("Chart.yaml", dir_of_file .. ";", -3)

    -- If Chart.yaml is found (path is not empty and not nil), set the filetype to helm.
    if chart_yaml_path and chart_yaml_path ~= "" then
      vim.bo[bufnr].filetype = "helm"
    end
  end,
})
