-- Enable syntax highlighting
vim.o.filetype = "plugin indent on"
vim.o.syntax = "enable"

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

-- Work in conjunction with base16-shell
vim.o.base16colorspace = 256

-- Enable true color support
vim.o.termguicolors = true
