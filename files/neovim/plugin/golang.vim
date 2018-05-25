let g:go_fmt_autosave = 0
let g:go_highlight_trailing_whitespace_error = 0

let g:deoplete#sources#go#gocode_binary = $GOPATH.'/bin/gocode'
let g:deoplete#sources#go#sort_class = ['package', 'func', 'type', 'var', 'const']
let g:LanguageClient_serverCommands.go = ['go-langserver']
