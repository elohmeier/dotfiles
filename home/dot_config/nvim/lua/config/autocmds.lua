-- Autocmd to set filetype to helm for Helm chart files
local helm_ft_group = vim.api.nvim_create_augroup("helm_filetype_detection", { clear = true })

vim.api.nvim_create_autocmd({ "BufNewFile", "BufRead" }, {
  group = helm_ft_group,
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
