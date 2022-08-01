require("telescope").load_extension("fzf")

telescope_builtin = require("telescope.builtin")
local bufopts = {noremap = true, silent = true, buffer = bufnr}
vim.keymap.set("n", "<leader>ff", telescope_builtin.find_files, bufopts)
vim.keymap.set("n", "<leader>fw", telescope_builtin.live_grep, bufopts)
