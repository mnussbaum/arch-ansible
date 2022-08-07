require("nvim-treesitter.configs").setup({
	ensure_installed = require("tree_sitter_plugins"),
	sync_install = false,
	auto_install = true,

	highlight = { enable = true },
})
