local specs = require("plugins")

-- Hooks must be registered before vim.pack.add().
-- Move hook fields into vim.pack's data field, which is accessible in PackChanged events.
local pack_specs = {}
for _, spec in ipairs(specs) do
	local data = {}
	if spec.post_hook_cmd then
		data.post_hook_cmd = spec.post_hook_cmd
	end
	if spec.post_hook_system then
		data.post_hook_system = spec.post_hook_system
	end
	table.insert(pack_specs, {
		src = spec.src,
		version = spec.version,
		data = next(data) and data or nil,
	})
end

vim.api.nvim_create_autocmd("PackChanged", {
	callback = function(ev)
		local kind = ev.data.kind
		if kind ~= "install" and kind ~= "update" then
			return
		end
		local data = ev.data.spec.data
		if not data then
			return
		end

		if data.post_hook_cmd then
			if not ev.data.active then
				vim.cmd.packadd(ev.data.spec.name)
			end
			vim.cmd(data.post_hook_cmd)
		end

		if data.post_hook_system then
			vim.system(vim.split(data.post_hook_system, " "), { cwd = ev.data.path }):wait()
		end
	end,
})

vim.pack.add(pack_specs)

-- Add commands as described in https://github.com/neovim/neovim/issues/34764

local function complete_packages()
	return vim.iter(vim.pack.get())
		:map(function(pack)
			return pack.spec.name
		end)
		:totable()
end

vim.api.nvim_create_user_command("PackUpdate", function(info)
	if #info.fargs ~= 0 then
		vim.pack.update(info.fargs, { force = info.bang })
	else
		vim.pack.update(nil, { force = info.bang })
	end
end, {
	desc = "Update packages",
	nargs = "*",
	bang = true,
	complete = complete_packages,
})

vim.api.nvim_create_user_command("PackDelete", function(info)
	vim.pack.del(info.fargs, { force = info.bang })
end, {
	desc = "Delete packages",
	nargs = "+",
	bang = true,
	complete = complete_packages,
})
