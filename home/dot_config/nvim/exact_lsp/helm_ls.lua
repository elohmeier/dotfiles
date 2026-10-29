return {
  cmd = { "helm_ls", "serve" },
  filetypes = { "helm" },
  root_markers = { "Chart.yaml" },
  settings = {
    ["helm-ls"] = {
      yamlls = {
        path = "yaml-language-server",
        enabled = true,
        diagnosticsLimit = 50,
        showDiagnosticsDirectly = false,
        config = {
          schemas = {
            ["https://raw.githubusercontent.com/argoproj/argo-workflows/refs/heads/main/api/jsonschema/schema.json"] = {
              "templates/workflows/*workflowtemplate.yaml",
            },
            kubernetes = {
              "templates/**/*.yaml",
              "!templates/workflows/*workflowtemplate.yaml",
            },
          },
          completion = true,
          hover = true,
        },
      },
    },
  },
}
