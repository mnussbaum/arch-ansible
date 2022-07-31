-- Disable backup
vim.o.noswapfile = true
vim.o.nobackup = true
vim.o.nowritebackup = true

-- Don't nag on leaving an unwritten file
vim.o.hidden = true

-- Persist undo history
silent !mkdir ~/.local/share/nvim/backups > /dev/null 2>&1
vim.o.undodir = ~/.local/share/nvim/backups
vim.o.undofile = true

-- Preserve lots of search and ex history
vim.o.history = 500

-- Preserve jump history
vim.o.shada = "'100,\"100,:20,%,n~/.local/share/nvim/shada/main.shada"

-- Restore cursor position on file reopen
vim.o.viewdir = "~/.local/share/nvim/view"
local resume_cursor_autogroup = nvim_create_augroup("resume_cursor")
nvim_create_autocmd("BufWinLeave", {
  pattern = "*",
  command = "silent! mkview",
  group = resume_cursor_autogroup,
})
nvim_create_autocmd("VimEnter", {
  pattern = "*",
  command = "silent! loadview",
  group = resume_cursor_autogroup,
})
