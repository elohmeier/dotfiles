-- Autocmd to set filetype to helm for Helm chart files
vim.api.nvim_create_autocmd({ "BufNewFile", "BufRead" }, {
  pattern = {
    "Chart.yaml",
    "values.yaml",
    "values.yml",
    "*/templates/*.yaml",
    "*/templates/*.tpl",
    "*/charts/*/templates/*.yaml",
    "*/charts/*/templates/*.tpl",
    "*/crds/*.yaml",
  },
  callback = function()
    vim.bo.filetype = "helm"
  end,
  desc = "Set filetype to helm for Helm chart files",
})
