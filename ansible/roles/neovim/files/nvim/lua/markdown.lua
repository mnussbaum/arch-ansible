-- Matches a list marker and its trailing space, plus an optional task box
local list_item = vim.regex([[^\s*\%([-*+]\|\d\+[.)]\)\s\+\%(\[.\]\s\+\)\?]])

-- Indents new lines to where the text of the list item above starts
function _G.markdown_indent()
	if list_item:match_str(vim.fn.getline(vim.v.lnum)) then
		return -1
	end

	local prev = vim.fn.prevnonblank(vim.v.lnum - 1)
	if prev == 0 then
		return 0
	end

	local _, text_col = list_item:match_str(vim.fn.getline(prev))

	return text_col or vim.fn.indent(prev)
end

vim.api.nvim_create_autocmd("FileType", {
	pattern = "markdown",
	callback = function()
		vim.bo.indentexpr = "v:lua.markdown_indent()"
	end,
})
