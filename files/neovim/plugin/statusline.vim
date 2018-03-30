call g:Base16hi("User1", g:base16_gui05, g:base16_gui0D, g:base16_cterm05, g:base16_cterm0D,"bold", "")
call g:Base16hi("User2", g:base16_gui05, g:base16_gui0C, g:base16_cterm05, g:base16_cterm0C,"bold", "")
call g:Base16hi("User3", g:base16_gui05, g:base16_gui01, g:base16_cterm05, g:base16_cterm01,"bold", "")
call g:Base16hi("User4", g:base16_gui05, g:base16_gui0F, g:base16_cterm05, g:base16_cterm0E,"bold", "")
call g:Base16hi("User5", g:base16_gui04, g:base16_gui02, g:base16_cterm04, g:base16_cterm02,"bold", "")
call g:Base16hi("User6", g:base16_gui05, g:base16_gui08, g:base16_cterm05, g:base16_cterm08,"bold", "")

function! g:File_write_status()
  let write_status = ""
  if &readonly
    let write_status = write_status . "RO "
  endif

  if &modified
    let write_status = write_status . "+ "
  endif

  if write_status != ""
    return "  " . write_status
  endif

  return ""
endfunction

function! g:Filetype_if_present()
  if &filetype != ""
    return "\ " . &filetype . "\ "
  endif

  return ""
endfunction

" Looks like:
"
" + plugin/statusline.vim  [vim]           5:21/36
" <file status> <file path> [<file type>]  <column>:<current line>/<total lines>
"
" Active lines are colorful, inactive lines are dark
function! g:ActiveStatusline()
  return "%6*%{g:File_write_status()}%1*\ %f\ %2*%{g:Filetype_if_present()}%3*%=%4*\ %c:%l/%L\ "
endfunction

function! g:InactiveStatusline()
  return "%5*%{g:File_write_status()}\ %f\ %{g:Filetype_if_present()}%=\ %c:%l/%L\ "
endfunction

set statusline=%!ActiveStatusline()

augroup statusline
  autocmd!
  autocmd WinEnter * setlocal statusline=%!ActiveStatusline()
  autocmd WinLeave * setlocal statusline=%!InactiveStatusline()
augroup END
