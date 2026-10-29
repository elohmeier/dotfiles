local dir = vim.fn.stdpath("state") .. "/sessions"
vim.fn.mkdir(dir, "p")
vim.opt.sessionoptions = { "blank", "buffers", "curdir", "folds", "tabpages", "winsize" }

local function save(path)
  vim.cmd.mksession({ path, bang = true, magic = { file = false }, mods = { silent = true } })
end

local function autosave()
  if vim.v.this_session ~= "" then
    save(vim.v.this_session)
  end
end

local function select(prompt, action)
  vim.ui.select(vim.fn.glob(dir .. "/*.vim", false, true), {
    prompt = prompt,
    format_item = function(path)
      return vim.fn.fnamemodify(path, ":t:r")
    end,
  }, function(path)
    if path then
      action(path)
    end
  end)
end

local timer = assert(vim.uv.new_timer())
timer:start(60000, 60000, vim.schedule_wrap(autosave))
vim.api.nvim_create_autocmd("VimLeavePre", {
  group = vim.api.nvim_create_augroup("config.sessions", { clear = true }),
  callback = function()
    timer:close()
    autosave()
    save(dir .. "/last.vim")
  end,
})

vim.keymap.set("n", "<leader>Ss", function()
  vim.ui.input({ prompt = "Save session: " }, function(name)
    if name and name ~= "" then
      save(dir .. "/" .. name .. ".vim")
    end
  end)
end, { desc = "Save Session" })
vim.keymap.set("n", "<leader>Sl", function()
  select("Load session: ", function(path)
    vim.cmd.source({ path, magic = { file = false } })
  end)
end, { desc = "Load Session" })
vim.keymap.set("n", "<leader>Sd", function()
  select("Delete session: ", function(path)
    vim.fn.delete(path)
    if vim.v.this_session == path then
      vim.v.this_session = ""
    end
  end)
end, { desc = "Delete Session" })
