let g:go_code_completion_enabled = 0
let g:go_def_mapping_enabled = 0
let g:go_fmt_autosave = 0
let g:go_highlight_build_constraints = 1
let g:go_highlight_extra_types = 1
let g:go_highlight_fields = 1
let g:go_highlight_functions = 1
let g:go_highlight_methods = 1
let g:go_highlight_operators = 1
let g:go_highlight_structs = 1
let g:go_highlight_trailing_whitespace_error = 0
let g:go_highlight_types = 1

autocmd BufWritePre *.go :CocCommand editor.action.organizeImport
