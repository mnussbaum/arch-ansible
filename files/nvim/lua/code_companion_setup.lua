require("codecompanion").setup({
	strategies = {
		chat = {
			adapter = "anthropic",
		},
		inline = {
			adapter = "anthropic",
		},
		cmd = {
			adapter = "anthropic",
		},
	},
})

vim.keymap.set({ "n", "v" }, "<C-c>", "<cmd>CodeCompanionActions<cr>", { noremap = true, silent = true })
vim.keymap.set({ "n", "v" }, "<LocalLeader>a", "<cmd>CodeCompanionChat Toggle<cr>", { noremap = true, silent = true })
vim.keymap.set("v", "ga", "<cmd>CodeCompanionChat Add<cr>", { noremap = true, silent = true })

-- Expand 'cc' into 'CodeCompanion' in the command line
vim.cmd([[cab cc CodeCompanion]])
