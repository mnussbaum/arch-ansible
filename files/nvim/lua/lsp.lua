-- Show diagnostics in the number column
vim.o.signcolumn = "number"

-- Configure hover delay for diagnostics
vim.o.updatetime = 300

local opts = { noremap = true, silent = true }
vim.keymap.set("n", "<space>e", vim.diagnostic.open_float, opts)
vim.keymap.set("n", "[d", vim.diagnostic.goto_prev, opts)
vim.keymap.set("n", "]d", vim.diagnostic.goto_next, opts)

local hover_diagnostics_autogroup = vim.api.nvim_create_augroup("hover_diagnostics", {})

-- Set up keymaps and autocmds when LSP attaches to a buffer
vim.api.nvim_create_autocmd("LspAttach", {
	callback = function(args)
		local bufnr = args.buf
		local bufopts = { noremap = true, silent = true, buffer = bufnr }

		-- LSP keymaps
		vim.keymap.set("n", "gD", vim.lsp.buf.declaration, bufopts)
		vim.keymap.set("n", "gd", vim.lsp.buf.definition, bufopts)
		vim.keymap.set("n", "gi", vim.lsp.buf.implementation, bufopts)
		vim.keymap.set("n", "gr", vim.lsp.buf.references, bufopts)
		vim.keymap.set("n", "gt", vim.lsp.buf.type_definition, bufopts)
		vim.keymap.set("n", "K", vim.lsp.buf.hover, bufopts)
		vim.keymap.set("n", "<C-k>", vim.lsp.buf.signature_help, bufopts)
		vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, bufopts)
		vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action, bufopts)
		vim.keymap.set("n", "<leader>f", vim.lsp.buf.format, bufopts)

		-- Show diagnostics on cursor hold
		vim.api.nvim_create_autocmd("CursorHold", {
			buffer = bufnr,
			callback = function()
				vim.diagnostic.open_float(nil, {
					focusable = false,
					scope = "line",
					close_events = {
						"CursorMoved",
						"CursorMovedI",
						"BufLeave",
						"BufHidden",
						"FocusLost",
						"InsertCharPre",
						"WinLeave",
					},
				})
			end,
			group = hover_diagnostics_autogroup,
		})

		-- Hide diagnostics when leaving buffer
		vim.api.nvim_create_autocmd("BufLeave", {
			buffer = bufnr,
			callback = function()
				-- Only close diagnostic floating windows, not all floating windows
				-- This prevents conflicts with Telescope and other plugins
				vim.diagnostic.hide(nil, bufnr)
			end,
			group = hover_diagnostics_autogroup,
		})
	end,
})

vim.diagnostic.config({
	virtual_text = false,
	signs = {
		text = {
			[vim.diagnostic.severity.ERROR] = " ",
			[vim.diagnostic.severity.WARN] = " ",
			[vim.diagnostic.severity.INFO] = "󰋼 ",
			[vim.diagnostic.severity.HINT] = "󰌵 ",
		},
		numhl = {
			[vim.diagnostic.severity.ERROR] = "",
			[vim.diagnostic.severity.WARN] = "",
			[vim.diagnostic.severity.HINT] = "",
			[vim.diagnostic.severity.INFO] = "",
		},
	},
	update_in_insert = true,
	underline = true,
	severity_sort = true,
	float = {
		focusable = false,
		style = "minimal",
		border = "rounded",
		source = "always",
		header = "",
		prefix = "",
		close_events = {
			"CursorMoved",
			"CursorMovedI",
			"BufLeave",
			"BufHidden",
			"FocusLost",
			"InsertCharPre",
			"WinLeave",
		},
	},
})

vim.lsp.handlers["textDocument/hover"] = vim.lsp.with(vim.lsp.handlers.hover, {
	border = "rounded",
	width = 60,
})

vim.lsp.handlers["textDocument/signatureHelp"] = vim.lsp.with(vim.lsp.handlers.signature_help, {
	border = "rounded",
	width = 60,
})

local cmp_lsp_capabilities = require("cmp_nvim_lsp").default_capabilities()

for language_server_name, language_server_setup in pairs(require("language_servers")) do
	-- Add custom overrides (like capabilities) if needed
	local config = vim.tbl_extend("force", { capabilities = cmp_lsp_capabilities }, language_server_setup)

	-- Only call vim.lsp.config if we have custom config beyond just capabilities
	if next(language_server_setup) ~= nil then
		vim.lsp.config(language_server_name, config)
	else
		vim.lsp.config(language_server_name, { capabilities = cmp_lsp_capabilities })
	end

	vim.lsp.enable(language_server_name)
end
