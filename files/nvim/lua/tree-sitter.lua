require("nvim-treesitter").setup({
	sync_install = false,
	auto_install = true,
	highlight = { enable = true },
})

local already_installed = require("nvim-treesitter.config").get_installed()
local to_install = vim.iter(require("tree_sitter_plugins"))
	:filter(function(parser)
		return not vim.tbl_contains(already_installed, parser)
	end)
	:totable()
require("nvim-treesitter").install(to_install)
