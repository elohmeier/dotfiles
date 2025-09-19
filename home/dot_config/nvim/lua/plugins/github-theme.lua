return {
  "projekt0n/github-nvim-theme",
  name = "github-theme",
  lazy = false, -- make sure we load this during startup if it is your main colorscheme
  priority = 1000, -- make sure to load this before all the other start plugins
  config = function()
    require("github-theme").setup({})

    -- Function to check macOS appearance and set theme accordingly
    local function check_appearance()
      -- Read macOS appearance setting
      local handle = io.popen("defaults read -g AppleInterfaceStyle 2>/dev/null")
      if handle then
        local result = handle:read("*a")
        handle:close()

        -- Trim whitespace and check result
        result = result:gsub("^%s*(.-)%s*$", "%1")

        if result == "Dark" then
          vim.cmd("colorscheme github_dark_default")
        else
          -- If not Dark or command fails, default to light
          vim.cmd("colorscheme github_light_default")
        end
      else
        -- Default to light if command fails
        vim.cmd("colorscheme github_light_default")
      end
    end

    -- Set initial theme based on system appearance
    check_appearance()

    -- Create autocmd to check appearance when Neovim gains focus
    vim.api.nvim_create_autocmd("FocusGained", {
      callback = check_appearance,
      desc = "Check system appearance and update theme",
    })

    -- Create user command for manual theme refresh
    vim.api.nvim_create_user_command("ThemeSync", check_appearance, {
      desc = "Sync theme with system appearance",
    })
  end,
}
