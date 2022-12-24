require("nvim-treesitter.configs").setup({
	ensure_installed = require("tree_sitter_plugins"),
	sync_install = false,
	auto_install = true,

	highlight = { enable = true },
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
