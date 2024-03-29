-- Show line numbers
vim.o.number = true

-- Set terminal/tmux title
vim.o.title = true

-- Show characters command will act on in bottom bar
vim.o.showcmd = true

-- Show cursor position in bottom bar
vim.o.ruler = true

-- Highlight 80th column and past
vim.cmd('let &colorcolumn="80,".join(range(120,999), ",")')

-- Enable true color support
vim.o.termguicolors = true

-- Use a block cursor in insert mode
vim.o.guicursor = "i:block"

require("base16-colorscheme").with_config({
	telescope = false,
	notify = true,
	cmp = true,
})
