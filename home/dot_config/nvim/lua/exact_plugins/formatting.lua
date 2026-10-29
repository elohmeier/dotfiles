vim.pack.add({ "https://github.com/stevearc/conform.nvim" })
local conform = require("conform")
conform.setup({
  formatters_by_ft = {
    astro = { "dprint" },
    bash = { "shfmt" },
    cpp = { "clang-format" },
    css = { "dprint" },
    hcl = { "packer_fmt" },
    html = { "dprint" },
    htmldjango = { "djade" },
    javascript = { "dprint" },
    json = { "dprint" },
    just = { "just" },
    jsonnet = { "jsonnetfmt" },
    lua = { "stylua" },
    markdown = { "rumdl" },
    nix = { "nixfmt" },
    puppet = { "puppet_fmt" },
    python = { "ruff_fix", "ruff_format" },
    ruby = { "rubocop" },
    sh = { "shfmt" },
    svelte = { "dprint" },
    terraform = { "tofu_fmt" },
    toml = { "taplo" },
    typescript = { "dprint" },
    typst = { "typstyle" },
    xml = { "xmllint" },
    yaml = { "dprint" },
    zsh = { "shfmt" },
    ["_"] = { "trim_whitespace" },
  },
  formatters = {
    dprint = {
      prepend_args = function(_, ctx)
        if not vim.fs.root(ctx.dirname, { "dprint.json", ".dprint.json", "dprint.jsonc", ".dprint.jsonc" }) then
          return { "--config", vim.fn.expand("~/.config/dprint.json") }
        end
        return {}
      end,
    },
    djade = {
      command = "djade",
      args = { "$FILENAME" },
      stdin = false,
      exit_codes = { 0, 1 },
    },
    ruff_fix = { append_args = { "--select", "I,UP" } },
    rumdl = { append_args = { "-d", "MD013" } },
    puppet_fmt = {
      command = "puppet-fmt",
      args = { "--indentation", "2", "--no-spacing" },
      stdin = true,
    },
    shfmt = { prepend_args = { "-i", "4" } },
  },
  format_on_save = function(bufnr)
    if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat then
      return
    end
    return { timeout_ms = 1500, lsp_format = "fallback" }
  end,
})

vim.api.nvim_create_user_command("FormatToggle", function(args)
  local scope = args.bang and vim.b or vim.g
  scope.disable_autoformat = not scope.disable_autoformat
  vim.notify(
    "Autoformat "
      .. (scope.disable_autoformat and "disabled" or "enabled")
      .. (args.bang and " for this buffer" or " globally")
  )
end, { desc = "Toggle autoformat-on-save", bang = true })

vim.opt.formatexpr = "v:lua.require'conform'.formatexpr()"
vim.keymap.set("n", "<leader>uf", "<cmd>FormatToggle<cr>", { desc = "Toggle Format" })
vim.keymap.set("n", "<leader>cf", conform.format, { desc = "Format Buffer" })
vim.keymap.set("x", "<leader>cF", conform.format, { desc = "Format Lines" })
