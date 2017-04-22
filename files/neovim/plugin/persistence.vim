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

" Preserve jump history
set shada='100,\"100,:20,%,n~/.local/share/nvim/shada/main.shada

" This function and augroup restore cursor position on file reopen
" Pulled from vim.wikia.com/wiki/Restore_cursor_to_file_position_in_previous_editing_session
function! ResCur()
  if line("'\"") <= line("$")
    normal! g`"
    return 1
  endif
endfunction

augroup resCur
  autocmd!
  autocmd BufWinEnter * call ResCur()
augroup END
