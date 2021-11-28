local tree_climber = require("tree-climber")
local keyopts = { noremap = true, silent = true }
vim.keymap.set({ "n", "v", "o" }, "th", tree_climber.goto_parent, keyopts)
vim.keymap.set({ "n", "v", "o" }, "tl", tree_climber.goto_child, keyopts)
vim.keymap.set({ "n", "v", "o" }, "tj", tree_climber.goto_next, keyopts)
vim.keymap.set({ "n", "v", "o" }, "tk", tree_climber.goto_prev, keyopts)
vim.keymap.set({ "n", "v", "o" }, "in", tree_climber.select_node, keyopts)

require("nvim-treesitter.configs").setup({
	textobjects = {
		swap = {
			enable = true,
			swap_next = {
				["ta"] = "@parameter.inner",
			},
			swap_previous = {
				["tA"] = "@parameter.inner",
			},
		},
	},
})

require("nvim-treesitter.configs").setup({
	textsubjects = {
		enable = true,
		prev_selection = ",",
		keymaps = {
			["."] = "textsubjects-smart",
			[";"] = "textsubjects-container-outer",
			["i;"] = "textsubjects-container-inner",
		},
	},
})
