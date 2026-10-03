-- Override nvim-base16 to look more like classic base16-vim
base16_colorscheme = require("base16-colorscheme")
local hi = require("base16-colorscheme").highlight

hi.LineNr = {
	guifg = base16_colorscheme.colors.base04,
	guibg = base16_colorscheme.colors.base01,
	gui = nil,
	guisp = nil,
}
hi.SignColumn = {
	guifg = base16_colorscheme.colors.base04,
	guibg = base16_colorscheme.colors.base01,
	gui = nil,
	guisp = nil,
}
hi.DiagnosticError = {
	guifg = base16_colorscheme.colors.base08,
	guibg = base16_colorscheme.colors.base01,
	gui = "none",
	guisp = nil,
}
hi.DiagnosticWarn = {
	guifg = base16_colorscheme.colors.base0E,
	guibg = base16_colorscheme.colors.base01,
	gui = "none",
	guisp = nil,
}
hi.DiagnosticInfo = {
	guifg = base16_colorscheme.colors.base05,
	guibg = base16_colorscheme.colors.base01,
	gui = "none",
	guisp = nil,
}
hi.DiagnosticHint = {
	guifg = base16_colorscheme.colors.base0C,
	guibg = base16_colorscheme.colors.base01,
	gui = "none",
	guisp = nil,
}
hi.VertSplit = {
	guifg = base16_colorscheme.colors.base02,
	guibg = base16_colorscheme.colors.base02,
	gui = "none",
	guisp = nil,
}
