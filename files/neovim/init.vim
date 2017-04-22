if &compatible
  set nocompatible
endif

source ~/.config/nvim/vim-plug.vim

let mapleader = "\\"

" Bash style file completion
set wildmode=longest,list

" Stop some commands from moving the cursor
set nostartofline

" Hide some prompts
set shortmess=atI

" Make Y work like other capitals, copy to end of line
noremap Y y$

" Save with sudo
:command! W w !sudo tee % > /dev/null

" Make esc fast
set timeoutlen=1000 ttimeoutlen=0
