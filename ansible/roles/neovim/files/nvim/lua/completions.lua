-- Bash style file completion
vim.o.wildmode = "longest,list"

vim.opt.completeopt = { "menu", "menuone", "noselect" }

local cmp = require("cmp")

local kind_icons = {
	Text = "",
	Method = "m",
	Function = "",
	Constructor = "",
	Field = "",
	Variable = "",
	Class = "",
	Interface = "",
	Module = "",
	Property = "",
	Unit = "",
	Value = "",
	Enum = "",
	Keyword = "",
	Snippet = "",
	Color = "",
	File = "",
	Reference = "",
	Folder = "",
	EnumMember = "",
	Constant = "",
	Struct = "",
	Event = "",
	Operator = "",
	TypeParameter = "",
}

cmp.setup({
	snippet = {
		expand = function(args)
			require("luasnip").lsp_expand(args.body)
		end,
	},

	formatting = {
		fields = { "menu", "abbr", "kind" },
		format = function(entry, item)
			local menu_icon = {
				nvim_lsp = "[LS]",
				buffer = "[B]",
				path = "[P]",
			}

			item.menu = menu_icon[entry.source.name]
			item.kind = string.format("%s", kind_icons[item.kind])

			return item
		end,
	},

	mapping = {
		["<C-n>"] = cmp.mapping(cmp.mapping.select_next_item(), { "i", "c" }),
		["<C-p>"] = cmp.mapping(cmp.mapping.select_prev_item(), { "i", "c" }),
		["<C-b>"] = cmp.mapping(cmp.mapping.scroll_docs(-4), { "i", "c" }),
		["<C-f>"] = cmp.mapping(cmp.mapping.scroll_docs(4), { "i", "c" }),
		["<C-Space>"] = cmp.mapping(cmp.mapping.complete(), { "i", "c" }),
		["<C-y>"] = cmp.config.disable, -- remove the default `<C-y>` mapping
		["<C-e>"] = cmp.mapping({
			i = cmp.mapping.abort(),
			c = cmp.mapping.close(),
		}),
		["<CR>"] = cmp.mapping.confirm({ select = true }), -- accept currently selected item
	},

	performance = {
		debounce = 300,
		throttle = 60,
		fetching_timeout = 200,
	},

	completion = { keyword_length = 3 },
	sources = {
		{ name = "path" },
		{ name = "nvim_lsp" },
		{ name = "treesitter", max_item_count = 10, keyword_length = 5 },
		{ name = "luasnip" },
		{ name = "emoji" },
	},
	window = {
		documentation = {
			border = { "╭", "─", "╮", "│", "╯", "─", "╰", "│" },
		},
	},
})

-- Search completions
cmp.setup.cmdline("/", {
	max_item_count = 12,
	sources = {
		{ name = "buffer", max_item_count = 10 },
		{ name = "cmdline_history" },
	},
})

cmp.setup.cmdline("?", {
	max_item_count = 12,
	sources = {
		{ name = "buffer", max_item_count = 10 },
		{ name = "cmdline_history" },
	},
})

-- Ex mode completions
cmp.setup.cmdline(":", {
	mapping = cmp.mapping.preset.cmdline(),
	sources = {
		{ name = "path" },
		{ name = "cmdline" },
	},
})
