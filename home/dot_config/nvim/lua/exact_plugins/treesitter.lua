vim.pack.add({
  "https://github.com/nvim-treesitter/nvim-treesitter",
  "https://github.com/nvim-treesitter/nvim-treesitter-context",
})

require("nvim-treesitter").install({
  "bash",
  "beancount",
  "c",
  "git_config",
  "git_rebase",
  "gitattributes",
  "gitcommit",
  "gitignore",
  "hcl",
  "helm",
  "javascript",
  "jsdoc",
  "json",
  "jsonnet",
  "just",
  "lua",
  "make",
  "markdown",
  "nix",
  "puppet",
  "python",
  "readline",
  "regex",
  "rhai",
  "ruby",
  "rust",
  "svelte",
  "terraform",
  "toml",
  "typescript",
  "typst",
  "vim",
  "vimdoc",
  "xml",
  "yaml",
})

vim.api.nvim_create_autocmd("FileType", {
  group = vim.api.nvim_create_augroup("config.treesitter", { clear = true }),
  callback = function(ev)
    local ft = vim.bo[ev.buf].filetype
    local lang = vim.treesitter.language.get_lang(ft)
    if not lang then
      return
    end
    if not pcall(vim.treesitter.start, ev.buf, lang) then
      return
    end
    if ft ~= "yaml" then
      vim.bo[ev.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
    end
  end,
})

require("treesitter-context").setup({})
vim.keymap.set("n", "<leader>tc", require("treesitter-context").toggle, { desc = "Toggle Treesitter Context" })
