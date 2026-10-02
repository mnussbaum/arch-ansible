-- Disable backup
vim.o.swapfile = false
vim.o.backup = false
vim.o.writebackup = false

-- Don't nag on leaving an unwritten file
vim.o.hidden = true

-- Persist undo history
vim.o.undofile = true

-- Preserve lots of search and ex history
vim.o.history = 500

-- Preserve jump history
vim.o.shada = "'100,\"100,:20,%"
