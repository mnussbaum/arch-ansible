require("arborist").setup({
	ensure_installed = require("tree_sitter_plugins"),
	ignore = { "startify" },
	-- markdown.lua sets its own list-aware indentexpr
	disable = { indent = { "markdown" } },
})
