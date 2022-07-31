-- Two space indent
vim.o.shiftwidth = 2
vim.o.tabstop = 2
vim.o.softtabstop = 2

-- Use spaces, not tabs
vim.o.expandtab = true
vim.o.smarttab = true

vim.o.autoindent = true

-- Text behaviour
-- vim.o.formatoptions = vim.o.formatoptions
--   + 't'    -- auto-wrap text using textwidth
--   + 'c'    -- auto-wrap comments using textwidth
--   + 'r'    -- auto insert comment leader on pressing enter
--   - 'o'    -- don't insert comment leader on pressing o
--   + 'q'    -- format comments with gq
--   - 'a'    -- don't autoformat the paragraphs (use some formatter instead)
--   + 'n'    -- autoformat numbered list
--   - '2'    -- I am a programmer and not a writer
--   + 'j'    -- Join comments smartly
vim.o.formatoptions = vim.o.formatoptions .. "tcrqnj"
