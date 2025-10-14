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
      -- Minimal options to save - reduces serialization time
      options = {
        "binary",
        "bufhidden",
        "buflisted",
        "filetype",
        "modifiable",
        "readonly",
      },
      -- Disable all extensions (including quickfix) for faster saves
      extensions = {},
      -- Filter out special buffers that shouldn't be saved
      buf_filter = function(bufnr)
        local buftype = vim.bo[bufnr].buftype
        local filetype = vim.bo[bufnr].filetype

        -- Exclude special buffer types
        if buftype ~= "" and buftype ~= "acwrite" then
          return false
        end

        -- Exclude neo-tree and other plugin buffers
        if
          filetype == "neo-tree"
          or filetype == "neo-tree-popup"
          or filetype == "TelescopePrompt"
          or filetype == "lazy"
          or filetype == "toggleterm"
          or filetype == "help"
        then
          return false
        end

        return true
      end,
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
