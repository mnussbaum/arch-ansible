runtime macros/matchit.vim

" Auto-format CSS on save
autocmd BufWritePre *.css :normal migg=G`i

let g:LanguageClient_serverCommands.css = ['css-languageserver', '--stdio']
let g:LanguageClient_serverCommands.html = ['html-languageserver', '--stdio']
