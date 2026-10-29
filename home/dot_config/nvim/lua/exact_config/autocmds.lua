local function helm(path)
  local chart = vim.fs.root(path, "Chart.yaml")
  if chart and vim.fs.relpath(chart, path):match("^templates/") then
    return "helm"
  end
end

vim.filetype.add({
  extension = { bean = "beancount", rhai = "rhai" },
  pattern = {
    [".*/templates/.*%.ya?ml"] = helm,
    [".*/templates/.*%.tpl"] = helm,
  },
})
