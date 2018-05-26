augroup formatting
  autocmd!
  autocmd BufWritePre * undjoin | Neoformat
augroup END
" augroup formatting
"   autocmd!
"   autocmd BufWritePre * call Format()<cr>
" augroup END
"
" " This function attempts to autcomplete using the language server client, and
" " then falls back to Neoformat
" function! Format()
"   try
"     call LanguageClient#textDocument_formatting()
"   catch
"     execute 'undojoin Neoformat'
"   endtry
" endfunction
