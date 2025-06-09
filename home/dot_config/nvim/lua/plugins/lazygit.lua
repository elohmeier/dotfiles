return {
  "kdheepak/lazygit.nvim",
  -- dependencies = {
  --   "nvim-lua/plenary.nvim",
  -- },
  config = function()
    -- Add keymapping
    vim.keymap.set("n", "<leader>gg", "<cmd>LazyGit<CR>", { desc = "Open LazyGit" })
  end,
}
