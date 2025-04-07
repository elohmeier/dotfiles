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

-- Map :W to :w (common typo) but only when it's the whole command
vim.cmd([[cnoreabbrev <expr> W ((getcmdtype() == ':' && getcmdline() == 'W') ? 'w' : 'W')]])

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
