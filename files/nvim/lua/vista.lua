vim.g["vista#renderer#enable_icon"] = 0
vim.g["vista_default_executive"] = "coc"
vim.g["vista_disable_statusline"] = 1
vim.g["vista_echo_cursor"] = 0
vim.g["vista_sidebar_width"] = 31
vim.g["vista_icon_indent"] = {"▸ ", ""}
vim.g["vista_echo_cursor_strategy"] = "floating_win"

vim.api.nvim_set_keymap(
  "n",
  "<leader>fd",
  ":Vista finder<CR>",
  { silent = true }
)
vim.api.nvim_set_keymap(
  "n",
  "<leader>vt",
  ":Vista!!<CR>",
  { silent = true }
)
