return {
  "dmtrKovalenko/fff.nvim",
  build = "OPENSSL_NO_VENDOR=1 cargo build --release",
  config = function()
    require("fff").setup({})

    -- keymaps
    vim.keymap.set("n", "<C-p>", function()
      require("fff").find_files()
    end, { desc = "Find files in current directory" })
  end,
}
