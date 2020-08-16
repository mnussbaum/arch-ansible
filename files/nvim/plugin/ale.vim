nnoremap <silent> K :ALEHover<CR>
nnoremap <silent> gd :ALEGoToDefinition<CR>
nnoremap <silent> gr  :ALEFindReferences<CR>
nnoremap <silent> <leader>at :ALEToggle<CR>

let g:ale_completion_enabled = 1

" We can skip slow python checks because we've installed neovim's python client
let g:loaded_python_provider = 1
let g:python3_host_prog  = "/usr/bin/python"
let g:python3_host_skip_check = 1
let g:python_host_prog = "/usr/bin/python2"
let g:python_host_skip_check=1

" Close the autocomplete window after completion is done
autocmd CompleteDone * silent! pclose!

" Avoid overly-aggressive autocomplete
" https://github.com/w0rp/ale/issues/1700
set completeopt=menu,menuone,preview,noselect,noinsert

let g:ale_enabled = 1
let g:ale_fix_on_save = 1
let g:ale_warn_about_trailing_blank_lines = 1
let g:ale_warn_about_trailing_whitespace = 1

" Don't show sign gutter, just highlight the line and show detail on hover
let g:ale_echo_cursor = 0
let g:ale_set_highlights = 1
let g:ale_set_signs = 0
let g:ale_virtualtext_cursor = 1
let g:ale_virtualtext_prefix = "▬▶  "
highlight link ALEErrorLine Error
highlight link ALEVirtualTextError ErrorMsg
highlight link ALEVirtualTextInfo ALEVirtualTextWarning
highlight link ALEVirtualTextStyleError ALEVirtualTextError
highlight link ALEVirtualTextStyleWarning ALEVirtualTextWarning
highlight link ALEVirtualTextWarning WarningMsg
highlight link ALEWarningLine WarningMsg

let g:ale_rust_rls_toolchain = ""
let g:ale_rust_rls_executable = "ra_lsp_server"

let g:ale_fixers = {
\  "c": ["clang-format"],
\  "css": ["prettier"],
\  "go": ["goimports", "gofmt"],
\  "graphql": ["prettier"],
\  "html": ["prettier"],
\  "javascript": ["prettier"],
\  "json": ["prettier"],
\  "markdown": ["prettier"],
\  "python": ["black"],
\  "ruby": ["rubocop"],
\  "rust": ["rustfmt"],
\  "scss": ["prettier"],
\  "yaml": ["prettier"]
\}

let g:ale_linters = {
\  "go": ["golint", "go vet", "golangserver"],
\  "python": ["pyls"],
\  "rust": ["analyzer"]
\}
