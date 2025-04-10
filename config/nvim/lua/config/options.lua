-- Relative line numbers
vim.opt.number = true
vim.opt.relativenumber = true

-- Set tabs to 4 spaces
vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.showtabline = 4
vim.opt.expandtab = true

-- Enable auto indenting and set it to spaces
vim.opt.smartindent = true
vim.opt.shiftwidth = 4

-- Enable smart indenting (see https://stackoverflow.com/questions/1204149/smart-wrap-in-vim)
vim.opt.breakindent = true

-- Enable incremental searching
vim.opt.hlsearch = true
vim.opt.incsearch = true

-- Enable text wrap
vim.opt.wrap = true

-- Better splitting
vim.opt.splitbelow = true
vim.opt.splitright = true

-- Enable mouse mode
vim.opt.mouse = "a" -- Mouse

-- Enable ignorecase + smartcase for better searching
vim.opt.ignorecase = true
vim.opt.smartcase = true -- Don't ignore case with capitals
vim.opt.grepprg = "rg --vimgrep"
vim.opt.grepformat = "%f:%l:%c:%m"

-- Decrease updatetime
vim.opt.updatetime = 50 -- faster completion (4000ms default)

-- Set completeopt to have a better completion experience
vim.opt.completeopt = { "menuone", "noselect", "noinsert" } -- mostly just for cmp

-- Enable persistent undo history
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.undofile = true

-- Enable 24-bit colors
vim.opt.termguicolors = true

-- Enable the sign column to prevent the screen from jumping
vim.opt.signcolumn = "yes"

-- Enable cursor line highlight
vim.opt.cursorline = true -- Highlight the line where the cursor is located

-- Set fold settings
-- These options were recommended by nvim-ufo
-- See: https://github.com/kevinhwang91/nvim-ufo#minimal-configuration
vim.opt.foldcolumn = "0"
vim.opt.foldlevel = 99
vim.opt.foldlevelstart = 99
vim.opt.foldenable = true

-- Always keep 8 lines above/below cursor unless at start/end of file
vim.opt.scrolloff = 8

-- Place a column line
vim.opt.colorcolumn = "80"

-- Set encoding type
vim.opt.encoding = "utf-8"
vim.opt.fileencoding = "utf-8"

-- Change cursor options
vim.opt.guicursor = {
  "n-v-c:block", -- Normal, visual, command-line: block cursor
  "i-ci-ve:block", -- Insert, command-line insert, visual-exclude: block cursor
  "r-cr:hor20", -- Replace, command-line replace: horizontal bar cursor with 20% height
  "o:hor50", -- Operator-pending: horizontal bar cursor with 50% height
  "a:blinkwait700-blinkoff400-blinkon250-Cursor/lCursor", -- All modes: blinking settings
  "sm:block-blinkwait175-blinkoff150-blinkon175", -- Showmatch: block cursor with specific blinking settings
}

-- Enable chars list
vim.opt.list = true -- Show invisible characters (tabs, eol, ...)
vim.opt.listchars = "tab:|->,lead:·,space: ,trail:•,extends:→,precedes:←,nbsp:␣"

-- More space in the neovim command line for displaying messages
vim.opt.cmdheight = 2

-- Maximum number of items to show in the popup menu (0 means "use available screen space")
vim.opt.pumheight = 0

-- Use conform-nvim for gq formatting
vim.opt.formatexpr = "v:lua.require'conform'.formatexpr()"

-- Global statusline
vim.opt.laststatus = 3 -- (https://neovim.io/doc/user/options.html#'laststatus')

-- Disable intro message
vim.opt.shortmess = "ltToOCFI" -- added I to disable intro message
