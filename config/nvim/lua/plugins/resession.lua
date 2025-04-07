return {
  "stevearc/resession.nvim",
  event = "VeryLazy",
  config = function()
    local resession = require("resession")

    resession.setup({
      autosave = {
        enabled = true,
        notify = false,
      },
    })

    -- Automatically save a session when you exit Neovim
    vim.api.nvim_create_autocmd("VimLeavePre", {
      callback = function()
        -- Always save a special session named "last"
        resession.save("last")
      end,
    })
  end,
  keys = {
    {
      "<leader>ss",
      "<cmd>lua require('resession').save()<cr>",
      desc = "Save Session",
      silent = true,
    },
    {
      "<leader>sl",
      "<cmd>lua require('resession').load()<cr>",
      desc = "Load Session",
      silent = true,
    },
    {
      "<leader>sd",
      "<cmd>lua require('resession').delete()<cr>",
      desc = "Delete Session",
      silent = true,
    },
  },
}
