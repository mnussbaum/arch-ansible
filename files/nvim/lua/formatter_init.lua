require("formatter").setup(require("formatters"))

local format_autogroup = vim.api.nvim_create_augroup("format", {})
vim.api.nvim_create_autocmd("BufWritePost", {
	pattern = "*",
	command = "FormatWrite",
	group = format_autogroup,
})
