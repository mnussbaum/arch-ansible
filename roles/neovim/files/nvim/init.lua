vim.g.mapleader = "\\"

vim.opt.mouse = ""

-- Make Y work like other capitals, copy to end of line
vim.api.nvim_set_keymap("n", "Y", "y$", { noremap = true })

-- Save with sudo
vim.cmd(":command! W w !sudo tee % > /dev/null")

-- Make esc fast
vim.o.ttimeoutlen = 0

-- Enable filetype declarations
vim.opt.modeline = true

-- Load plugins before sourcing other config files
vim.cmd("source ~/.config/nvim/lua/pack_init.lua")

-- Source all lua directory files except pack_init which is loaded above
local paths = vim.split(vim.fn.glob("~/.config/nvim/lua/*lua"), "\n")

for i, file in pairs(paths) do
	if not file:match("pack_init%.lua$") then
		vim.cmd("source " .. file)
	end
end
