nnoremap <silent> K :ALEHover<CR>
nnoremap <silent> gd :ALEGoToDefinition<CR>
nnoremap <silent> gr  :ALEFindReferences<CR>

let g:ale_completion_enabled = 1
let g:ale_enabled = 1
let g:ale_fix_on_save = 1
let g:ale_rust_rls_toolchain = ""
let g:ale_sign_column_always = 1

let g:ale_fixers = {
\  'css': ['prettier'],
\  'go': ['goimports', 'gofmt'],
\  'html': ['prettier'],
\  'javascript': ['prettier'],
\  'json': ['jq'],
\  'python': ['black'],
\  'ruby': ['rubocop'],
\  'rust': ['rustfmt'],
\  'scss': ['prettier']
\}

let g:ale_linters = {
\  'go': ['golint', 'go vet', 'golangserver'],
\  'python': ['pyls'],
\  'rust': ['rls']
\}
