-- vim.pack.add() was already called by pack_init.lua before this script runs.
-- It fires PackChanged events as it installs plugins. Wait for those to finish
-- by resetting a quit timer on each event and quitting when it expires.
local timer = assert(vim.uv.new_timer())

local function quit()
	timer:close()
	vim.cmd("qall")
end

vim.api.nvim_create_autocmd("PackChanged", {
	callback = function()
		timer:stop()
		timer:start(2000, 0, vim.schedule_wrap(quit))
	end,
})

timer:start(2000, 0, vim.schedule_wrap(quit))
