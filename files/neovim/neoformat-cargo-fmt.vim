function! neoformat#formatters#rs#enabled() abort
  return ['cargo_fmt']
endfunction

function! neoformat#formatters#rs#cargo_fmt() abort
  return {
        \ 'exe': 'cargo-fmt',
        \ 'args': ['--'],
        \ 'stdin': 1
        \ }
endfunction
