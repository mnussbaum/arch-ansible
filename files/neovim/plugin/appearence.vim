" Enable syntax highlighting
filetype plugin indent on
syntax enable

" Highlight on save
let g:highlighter#auto_update = 1

" Show line numbers
set number

" Set terminal/tmux title
set title

" Show characters command will act on in bottom bar
set showcmd

" Show cursor position in bottom bar
set ruler

" Highlight 80th column
let &colorcolumn="80,".join(range(120,999), ",")

" Work in conjunction with base16-shell
let base16colorspace=256

" Enable true color support
set termguicolors
