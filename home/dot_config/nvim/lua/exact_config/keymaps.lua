vim.keymap.set("x", "<leader>p", '"_dP')

vim.keymap.set({ "n", "v" }, "<leader>y", '"+y')
vim.keymap.set("n", "<leader>Y", '"+Y')
vim.keymap.set("n", "<leader>p", '"+p')

vim.keymap.set({ "n", "v" }, "<leader>d", '"_d')

vim.keymap.set("i", "<C-c>", "<Esc>")

vim.keymap.set("n", "Q", "<nop>")

-- Readline shortcuts using native motions; keep the built-in Ctrl-W/Ctrl-U.
for lhs, rhs in pairs({
  ["<M-f>"] = "<C-Right>",
  ["<M-b>"] = "<C-Left>",
  ["<C-a>"] = "<Home>",
  ["<C-e>"] = "<End>",
  ["<M-BS>"] = "<C-w>",
}) do
  vim.keymap.set("!", lhs, rhs)
end
vim.keymap.set("i", "<M-d>", function()
  return vim.fn.col(".") > #vim.fn.getline(".") and "<Del>" or "<C-o>dw"
end, { expr = true })
vim.keymap.set("i", "<C-k>", function()
  return vim.fn.col(".") > #vim.fn.getline(".") and "" or "<C-o>D"
end, { expr = true })
vim.keymap.set("c", "<C-k>", function()
  vim.fn.setcmdline(vim.fn.getcmdline():sub(1, vim.fn.getcmdpos() - 1))
end)
vim.keymap.set("c", "<M-d>", function()
  local line, pos = vim.fn.getcmdline(), vim.fn.getcmdpos()
  local stop = vim.fn.matchend(line, [[\W*\w*]], pos - 1)
  vim.fn.setcmdline(line:sub(1, pos - 1) .. line:sub(stop + 1), pos)
end)
vim.keymap.set("i", "<C-Space>", "<C-n>", { desc = "Complete" })

-- Map :W to :w and :Q to :q (common typos) but only when they're the whole command
vim.cmd([[cnoreabbrev <expr> W ((getcmdtype() == ':' && getcmdline() == 'W') ? 'w' : 'W')]])
vim.cmd([[cnoreabbrev <expr> Q ((getcmdtype() == ':' && getcmdline() == 'Q') ? 'q' : 'Q')]])
vim.cmd([[cnoreabbrev <expr> Qa ((getcmdtype() == ':' && getcmdline() == 'Qa') ? 'qa' : 'Qa')]])

-- Option + Shift + w to insert „ (like in macOS)
vim.keymap.set("i", "<M-S-w>", "„")

-- Option + [ to insert " (like in macOS)
vim.keymap.set("i", "<M-[>", '"')

-- Option + u followed by a,o,u,A,O,U to insert ä,ö,ü,Ä,Ö,Ü (like in macOS)
vim.keymap.set("i", "<M-u>a", "ä")
vim.keymap.set("i", "<M-u>o", "ö")
vim.keymap.set("i", "<M-u>u", "ü")
vim.keymap.set("i", "<M-u>A", "Ä")
vim.keymap.set("i", "<M-u>O", "Ö")
vim.keymap.set("i", "<M-u>U", "Ü")

-- Option + s insert ß (like in macOS)
vim.keymap.set("i", "<M-s>", "ß")

-- Copy current file path to clipboard
vim.keymap.set("n", "<leader>cy", function()
  local filepath = vim.fn.expand("%:p")
  if filepath == "" then
    vim.notify("No file name to copy", vim.log.levels.WARN)
    return
  end
  vim.fn.setreg("+", filepath)
  vim.notify("Copied file path to clipboard: " .. filepath, vim.log.levels.INFO)
end, { desc = "Copy File Path to Clipboard", silent = true })
