vim.o.test#strategy = "vtr"

-- Run all
vim.api.nvim_set_keymap(
  "n",
  "<leader>ra",
  ":TestSuite<CR>",
  { silent = true }
)

-- Run buffer
vim.api.nvim_set_keymap(
  "n",
  "<leader>rb",
  ":TestFile<CR>",
  { silent = true }
)

-- Run focused
vim.api.nvim_set_keymap(
  "n",
  "<leader>rf",
  ":TestNearest<CR>",
  { silent = true }
)

-- Run last
vim.api.nvim_set_keymap(
  "n",
  "<leader>rl",
  ":TestLast<CR>",
  { silent = true }
)
