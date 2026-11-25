-- Run in the guest as the user, after the image's config has loaded:
--   NVIM_CHECK_DIR=... NVIM_CHECK_OUT=... nvim --headless -c "luafile nvim_check.lua"
-- Writes what it found to $NVIM_CHECK_OUT as JSON and quits. Each step runs
-- protected, so an error in one is recorded and the rest still report.
local dir = assert(os.getenv("NVIM_CHECK_DIR"))
local out = assert(os.getenv("NVIM_CHECK_OUT"))
local result = {
	plugins = {},
	inactive_plugins = {},
	lsp = {},
	fixed_script = "",
	check_errors = {},
}

local function step(name, fn)
	local ok, err = pcall(fn)
	if not ok then
		table.insert(result.check_errors, name .. ": " .. tostring(err))
	end
end

-- Startup
step("startup", function()
	for _, plugin in ipairs(vim.pack.get()) do
		table.insert(result.plugins, plugin.spec.name)
		if not plugin.active then
			table.insert(result.inactive_plugins, plugin.spec.name)
		end
	end
end)

-- Language servers: wait for the expected one, then list all that attached.
local function attached(path, expected)
	vim.cmd.edit(path)
	local buf = vim.api.nvim_get_current_buf()
	vim.wait(90000, function()
		return #vim.lsp.get_clients({ bufnr = buf, name = expected }) > 0
	end, 500)
	local names = {}
	for _, client in ipairs(vim.lsp.get_clients({ bufnr = buf })) do
		table.insert(names, client.name)
	end
	return { filetype = vim.bo[buf].filetype, clients = names }
end

step("ansible lsp", function()
	result.lsp.ansible = attached(dir .. "/roles/demo/tasks/main.yml", "ansiblels")
end)
step("python lsp", function()
	result.lsp.python = attached(dir .. "/demo.py", "pyright")
end)

-- Format on save: conform's shellcheck fixer.
step("format on save", function()
	vim.cmd.edit(dir .. "/fix.sh")
	vim.cmd.write()
	result.fixed_script = table.concat(vim.fn.readfile(dir .. "/fix.sh"), "\n")
end)

-- Last, so errors raised by any step above are in them.
result.errmsg = vim.v.errmsg
result.messages = vim.api.nvim_exec2("messages", { output = true }).output

vim.fn.writefile({ vim.json.encode(result) }, out)
vim.cmd("qall!")
