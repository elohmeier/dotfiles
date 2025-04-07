return {
  "ibhagwan/fzf-lua",
  -- optional for icon support
  dependencies = { "nvim-tree/nvim-web-devicons" },
  config = function()
    -- configure fzf-lua
    require("fzf-lua").setup({
      -- add any custom configuration here
    })

    -- keymaps
    vim.keymap.set("n", "<leader>ff", "<cmd>FzfLua files<cr>", { desc = "Find project files" })
  end,
}
