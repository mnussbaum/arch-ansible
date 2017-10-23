let g:deoplete#enable_at_startup = 1

" We can skip slow python checks because we've installed neovim's python client
let g:loaded_python_provider = 1
let g:python3_host_prog  = '/usr/bin/python'
let g:python3_host_skip_check = 1
let g:python_host_prog = '/usr/bin/python2'
let g:python_host_skip_check=1

" Close the autocomplete window after completion is done
autocmd CompleteDone * silent! pclose!
