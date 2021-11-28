vim.cmd([[packadd packer.nvim]])

return require("packer").startup(function(use)
	for _, plugin in ipairs(require("plugins")) do
		use(plugin)
	end
end)
