vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true
vim.opt.smartindent = true
vim.opt.breakindent = true
vim.opt.splitbelow = true
vim.opt.splitright = true
vim.opt.mouse = "a"
vim.opt.ignorecase = true
vim.opt.smartcase = true
vim.opt.grepprg = "rg --vimgrep"
vim.opt.updatetime = 250 -- Delay before document highlights and notebook sync checks.
vim.opt.swapfile = false
vim.opt.undofile = true
vim.opt.termguicolors = true
vim.opt.signcolumn = "yes"
vim.opt.cursorline = true
vim.opt.foldlevel = 99
vim.opt.foldlevelstart = 99
vim.opt.scrolloff = 8
vim.opt.colorcolumn = "80"
vim.opt.fileencoding = "utf-8"
vim.opt.guicursor = {
  "n-v-c:block",
  "i-ci-ve:block",
  "r-cr:hor20",
  "o:hor50",
  "a:blinkwait700-blinkoff400-blinkon250-Cursor/lCursor",
  "sm:block-blinkwait175-blinkoff150-blinkon175",
}
vim.opt.list = true
vim.opt.listchars = "tab:|->,lead:·,space: ,trail:•,extends:→,precedes:←,nbsp:␣"
vim.opt.cmdheight = 2
vim.opt.showtabline = 2
vim.opt.laststatus = 3 -- Use Neovim's default statusline across the whole window.
vim.opt.shortmess:append("I")
