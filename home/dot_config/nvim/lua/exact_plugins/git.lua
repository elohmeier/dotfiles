vim.pack.add({
  "https://github.com/lewis6991/gitsigns.nvim",
  "https://github.com/rafikdraoui/jj-diffconflicts",
})

require("gitsigns").setup({
  on_attach = function(bufnr)
    if vim.api.nvim_buf_get_name(bufnr):match("%.ipynb$") then
      return false
    end
  end,
})
vim.cmd.packadd("nvim.difftool")

vim.keymap.set("n", "<leader>ghb", "<cmd>Gitsigns blame_line<cr>", { desc = "Blame Line" })
vim.keymap.set("n", "<leader>ghd", "<cmd>Gitsigns diffthis<cr>", { desc = "Diff This" })
vim.keymap.set("n", "<leader>ghp", "<cmd>Gitsigns preview_hunk<cr>", { desc = "Preview Hunk" })
vim.keymap.set("n", "<leader>ghR", "<cmd>Gitsigns reset_buffer<cr>", { desc = "Reset Buffer" })
vim.keymap.set({ "n", "v" }, "<leader>ghr", ":Gitsigns reset_hunk<cr>", { desc = "Reset Hunk", silent = true })
vim.keymap.set({ "n", "v" }, "<leader>ghs", ":Gitsigns stage_hunk<cr>", { desc = "Stage Hunk", silent = true })
vim.keymap.set("n", "<leader>ghS", "<cmd>Gitsigns stage_buffer<cr>", { desc = "Stage Buffer" })
vim.keymap.set("n", "<leader>ghu", "<cmd>Gitsigns undo_stage_hunk<cr>", { desc = "Undo Stage Hunk" })

vim.api.nvim_create_user_command("LazyGit", function()
  vim.cmd.tabnew()
  vim.fn.jobstart({ "lazygit" }, { term = true })
  vim.cmd.startinsert()
end, { desc = "Open LazyGit in a terminal tab" })
vim.keymap.set("n", "<leader>gg", "<cmd>LazyGit<cr>", { desc = "Open LazyGit" })
