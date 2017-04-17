" Disable backup
set noswapfile
set nobackup
set nowritebackup

" Persist undo history
silent !mkdir ~/.local/share/nvim/backups > /dev/null 2>&1
set undodir=~/.local/share/nvim/backups
set undofile

" Preserve lots of search and ex history
set history=500
