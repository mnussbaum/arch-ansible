let g:vista#renderer#enable_icon = 0
let g:vista_default_executive = "coc"
let g:vista_disable_statusline = 1
let g:vista_echo_cursor = 0
let g:vista_sidebar_width = 31
let g:vista_icon_indent = ["▸ ", ""]

" Remove this exists check in nvim 0.4+
if exists("*nvim_open_win")
  let g:vista_echo_cursor_strategy = "floating_win"
endif

nnoremap <silent> <leader>fd :Vista finder<CR>
nnoremap <silent> <leader>vt :Vista!!<CR>
