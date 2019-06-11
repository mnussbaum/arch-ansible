let g:lightline = {
      \ 'colorscheme': 'base16_base16_oceanic_next',
      \ 'separator': {'left': "\ue0bc", 'right': "\ue0ba"},
      \ 'subseparator': {'left': "\ue0bb", 'right': "\ue0bb"},
      \ 'tabline_separator': {'left': "\ue0bc", 'right': "\ue0ba"},
      \ 'tabline_subseparator': {'left': "\ue0bb", 'right': "\ue0bb"},
      \ 'active': {
      \   'left': [['readonly', 'modified'], ['filename']],
      \   'right': [['percent', 'lineinfo' ]]
      \  }
      \ }
