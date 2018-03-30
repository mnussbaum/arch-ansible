let g:fzf_layout = { 'up': '~20%' }

command! -bang -nargs=* Rg
  \ call fzf#vim#grep(
  \   'rg --column --line-number --no-heading --color=always --follow --hidden --ignore-case '.shellescape(<q-args>), 1,
  \   <bang>0 ? fzf#vim#with_preview('up:60%')
  \           : fzf#vim#with_preview('right:50%:hidden', '?'),
  \   <bang>0)

map <silent> <leader>ff :Rg<CR>

set grepprg=rg\g--vimgrep\ --no-heading
set grepformat=%f:%l:%c:%m,%f:%l:%m
