" When writing a buffer.
call neomake#configure#automake('w')
" When writing a buffer, and on normal mode changes (after 750ms).
call neomake#configure#automake('nw', 750)
" When reading a buffer (after 1s), and when writing.
call neomake#configure#automake('rw', 1000)

" Hack to stop Neomake running when exitting because it creates a zombie cargo
" check process which holds the lock and never exits. But then, if you only
" have QuitPre, closing one pane will disable neomake, so BufEnter reenables
" when you enter another buffer.
" From http://seenaburns.com/vim-setup-for-rust/

let s:quitting = 0
au QuitPre *.rs let s:quitting = 1
au BufEnter *.rs let s:quitting = 0
au BufWritePost *.rs if ! s:quitting | Neomake | else | echom "Neomake disabled"| endif
let g:neomake_warning_sign = {'text': '?'}
