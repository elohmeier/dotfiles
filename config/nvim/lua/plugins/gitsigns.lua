return {
  "lewis6991/gitsigns.nvim",
  event = { "BufReadPre", "BufNewFile" },
  opts = {
    current_line_blame = false,
  },
  keys = {
    -- Leader menu for hunks
    { "<leader>gh", desc = "+hunks" },
    
    -- Blame line
    { "<leader>ghb", ":Gitsigns blame_line<CR>", desc = "Blame line", silent = true },
    
    -- Diff this
    { "<leader>ghd", ":Gitsigns diffthis<CR>", desc = "Diff This", silent = true },
    
    -- Preview hunk
    { "<leader>ghp", ":Gitsigns preview_hunk<CR>", desc = "Preview hunk", silent = true },
    
    -- Reset buffer
    { "<leader>ghR", ":Gitsigns reset_buffer<CR>", desc = "Reset Buffer", silent = true },
    
    -- Reset hunk (normal and visual mode)
    { "<leader>ghr", ":Gitsigns reset_hunk<CR>", desc = "Reset Hunk", silent = true, mode = { "n", "v" } },
    
    -- Stage hunk (normal and visual mode)
    { "<leader>ghs", ":Gitsigns stage_hunk<CR>", desc = "Stage Hunk", silent = true, mode = { "n", "v" } },
    
    -- Stage buffer
    { "<leader>ghS", ":Gitsigns stage_buffer<CR>", desc = "Stage Buffer", silent = true },
    
    -- Undo stage hunk
    { "<leader>ghu", ":Gitsigns undo_stage_hunk<CR>", desc = "Undo Stage Hunk", silent = true },
  },
}
