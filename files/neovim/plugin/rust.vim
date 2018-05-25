if executable('racer')
  let g:deoplete#sources#rust#racer_binary = systemlist('which racer')[0]
endif

if executable('rustc')
  " if src installed via rustup, we can get it by running
  " rustc --print sysroot then appending the rest of the path
  let rustc_root = systemlist('rustc --print sysroot')[0]
  let rustc_src_dir = rustc_root . '/lib/rustlib/src/rust/src'
  if isdirectory(rustc_src_dir)
    let g:deoplete#sources#rust#rust_source_path = rustc_src_dir
  endif
endif

let g:LanguageClient_serverCommands.rust = ['rustup', 'run', 'nightly', 'rls']
