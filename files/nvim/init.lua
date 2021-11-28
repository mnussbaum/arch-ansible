require("plugins")

vim.g.mapleader = "\\"

-- Bash style file completion
vim.o.wildmode = "longest,list"

-- Make Y work like other capitals, copy to end of line
vim.api.nvim_set_keymap("n", "Y", "y$", { noremap = true })

-- Save with sudo
vim.cmd(":command! W w !sudo tee % > /dev/null")

-- Make esc fast
vim.o.ttimeoutlen = 0

-- Source all lua directory files
local paths = vim.split(vim.fn.glob("~/.config/nvim/lua/*lua"), "\n")

for i, file in pairs(paths) do
	vim.cmd("source " .. file)
end
