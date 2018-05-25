augroup neoformat
  autocmd!
  autocmd BufWritePre * undojoin | silent Neoformat
augroup END
