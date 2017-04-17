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

" Reopen file to same cursor location
au BufReadPost * if line("'\"") > 0|if line("'\"") <=line("$")|exe("norm'\"")|else|exe "norm $"|endif|endif

" Make Y work like other capitals, copy to end of line
noremap Y y$

" Save with sudo
:command! W w !sudo tee % > /dev/null
