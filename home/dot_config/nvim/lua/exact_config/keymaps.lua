-- greatest remap ever
vim.keymap.set("x", "<leader>p", '"_dP')

-- next greatest remap ever : asbjornHaland
vim.keymap.set({ "n", "v" }, "<leader>y", '"+y')
vim.keymap.set("n", "<leader>Y", '"+Y')
vim.keymap.set("n", "<leader>p", '"+p')

vim.keymap.set({ "n", "v" }, "<leader>d", '"_d')

-- This is going to get me cancelled
vim.keymap.set("i", "<C-c>", "<Esc>")

vim.keymap.set("n", "Q", "<nop>")

-- Map :W to :w and :Q to :q (common typos) but only when they're the whole command
vim.cmd([[cnoreabbrev <expr> W ((getcmdtype() == ':' && getcmdline() == 'W') ? 'w' : 'W')]])
vim.cmd([[cnoreabbrev <expr> Q ((getcmdtype() == ':' && getcmdline() == 'Q') ? 'q' : 'Q')]])
vim.cmd([[cnoreabbrev <expr> Qa ((getcmdtype() == ':' && getcmdline() == 'Qa') ? 'qa' : 'Qa')]])

-- Option + Shift + w to insert „ (like in macOS)
vim.keymap.set("i", "<M-S-w>", "„", { noremap = true, silent = true })

-- Option + [ to insert " (like in macOS)
vim.keymap.set("i", "<M-[>", '"', { noremap = true, silent = true })

-- Option + u followed by a,o,u,A,O,U to insert ä,ö,ü,Ä,Ö,Ü (like in macOS)
vim.keymap.set("i", "<M-u>a", "ä", { noremap = true, silent = true })
vim.keymap.set("i", "<M-u>o", "ö", { noremap = true, silent = true })
vim.keymap.set("i", "<M-u>u", "ü", { noremap = true, silent = true })
vim.keymap.set("i", "<M-u>A", "Ä", { noremap = true, silent = true })
vim.keymap.set("i", "<M-u>O", "Ö", { noremap = true, silent = true })
vim.keymap.set("i", "<M-u>U", "Ü", { noremap = true, silent = true })

-- Option + s insert ß (like in macOS)
vim.keymap.set("i", "<M-s>", "ß", { noremap = true, silent = true })

-- Ctrl + a in command mode to go to the beginning of the line
vim.keymap.set("c", "<C-a>", "<C-b>", { noremap = true, silent = false })

-- Copy current file path to clipboard
vim.keymap.set("n", "<leader>cy", function()
  local filepath = vim.fn.expand("%:p")
  if filepath == "" or vim.fn.empty(filepath) == 1 then
    vim.notify("No file name to copy", vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", filepath)
  vim.notify("Copied file path to clipboard: " .. filepath, vim.log.levels.INFO)
end, { desc = "Copy File Path to Clipboard", silent = true })
