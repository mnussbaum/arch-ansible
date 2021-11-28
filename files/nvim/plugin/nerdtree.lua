vim.api.nvim_set_keymap(
  "n",
  "<leader>nt",
  ":NERDTreeToggle<CR>",
  { silent = true }
)
vim.api.nvim_set_keymap(
  "n",
  "<leader>nf",
  ":NERDTreeFind<CR>",
  { silent = true }
)
vim.o.NERDTreeShowHidden = 1
