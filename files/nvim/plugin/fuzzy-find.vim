function! FloatingFZF()
  let buffer = nvim_create_buf(v:false, v:true)
  let height = float2nr(&lines * 0.33)
  let width = float2nr(&columns * 0.75)
  let horizontal_position = float2nr((&columns - width) / 2)

  let opts = {
        \ "relative": "editor",
        \ "row": 0,
        \ "col": horizontal_position,
        \ "width": width,
        \ "height": height
        \ }

  let window = nvim_open_win(buffer, v:true, opts)
  call nvim_win_set_option(window, "winblend", 15)
endfunction

let g:fzf_layout = { "window": "call FloatingFZF()" }

command! -bang -nargs=* Rg
  \ call fzf#vim#grep(
  \   "rg --column --line-number --no-heading --color=always --follow --hidden --ignore-case --glob '!.git/' ".shellescape(<q-args>), 1,
  \   <bang>0 ? fzf#vim#with_preview("up:60%")
  \           : fzf#vim#with_preview("right:50%:hidden", "?"),
  \   <bang>0)

map <silent> <leader>ff :Rg<CR>

set grepprg=rg\g--vimgrep\ --no-heading
set grepformat=%f:%l:%c:%m,%f:%l:%m
