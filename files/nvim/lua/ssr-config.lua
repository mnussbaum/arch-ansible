vim.keymap.set({ "n", "x" }, "<leader>sr", function()
	ssr = require("ssr")
	ssr.setup({
		border = "rounded",
		min_width = 50,
		min_height = 5,
		max_width = 120,
		max_height = 25,
		adjust_window = true,
		keymaps = {
			close = "q",
			next_match = "n",
			prev_match = "N",
			replace_confirm = "<cr>",
			replace_all = "<leader><cr>",
		},
	})

	ssr.open()
end)
