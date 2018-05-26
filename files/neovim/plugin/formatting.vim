function! s:lang_client_format_sync(...) abort
  call LanguageClient_runSync('LanguageClient#textDocument_formatting', {
        \ 'handle': v:true,
        \ })
endfunction

set formatexpr=LanguageClient#textDocument_rangeFormatting_sync()
let g:lang_server_format_filetypes = ['ruby', 'rust']

function! Format()
  if index(g:lang_server_format_filetypes, &ft) >= 0
    call s:lang_client_format_sync()
  else
    execute 'silent Neoformat'
  endif
endfunction

augroup formatting
  autocmd!
  autocmd BufWritePre * call Format()
augroup END
