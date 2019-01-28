nnoremap <silent> K :ALEHover<CR>
nnoremap <silent> gd :ALEGoToDefinition<CR>
nnoremap <silent> gr  :ALEFindReferences<CR>

let g:ale_completion_enabled = 1
let g:ale_enabled = 1
let g:ale_fix_on_save = 1
let g:ale_rust_rls_toolchain = ""
let g:ale_warn_about_trailing_blank_lines = 1
let g:ale_warn_about_trailing_whitespace = 1

" Don't show sign gutter, just highlight the line and show detail on hover
let g:ale_echo_cursor = 0
let g:ale_set_highlights = 1
let g:ale_set_signs = 0
let g:ale_virtualtext_cursor = 1
let g:ale_virtualtext_prefix = '▬▶  '
highlight link ALEErrorLine Error
highlight link ALEVirtualTextError ErrorMsg
highlight link ALEVirtualTextInfo ALEVirtualTextWarning
highlight link ALEVirtualTextStyleError ALEVirtualTextError
highlight link ALEVirtualTextStyleWarning ALEVirtualTextWarning
highlight link ALEVirtualTextWarning WarningMsg
highlight link ALEWarningLine WarningMsg

let g:ale_fixers = {
\  'css': ['prettier'],
\  'go': ['goimports', 'gofmt'],
\  'graphql': ['prettier'],
\  'html': ['prettier'],
\  'javascript': ['prettier'],
\  'json': ['prettier'],
\  'markdown': ['prettier'],
\  'python': ['black'],
\  'ruby': ['rubocop'],
\  'rust': ['rustfmt'],
\  'scss': ['prettier'],
\  'yaml': ['prettier']
\}

let g:ale_linters = {
\  'go': ['golint', 'go vet', 'golangserver'],
\  'python': ['pyls'],
\  'rust': ['rls']
\}
