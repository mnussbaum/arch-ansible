" Disable backup
set noswapfile
set nobackup
set nowritebackup

" Don't nag on leaving an unwritten file
set hidden

" Persist undo history
silent !mkdir ~/.local/share/nvim/backups > /dev/null 2>&1
set undodir=~/.local/share/nvim/backups
set undofile

" Preserve lots of search and ex history
set history=500

" Preserve jump history
set shada='100,\"100,:20,%,n~/.local/share/nvim/shada/main.shada

" Restore cursor position on file reopen
" Pulled from https://stackoverflow.com/questions/8854371/vim-how-to-restore-the-cursors-logical-and-physical-positions
augroup resCur
  autocmd!
  autocmd BufWinLeave * silent! mkview
  autocmd VimEnter * silent! loadview
augroup END
set viewdir=~/.local/share/nvim/view
