local M = {}

function M.create_augroup(autocmds, name)
    vim.cmd("augroup " .. name)
    vim.cmd("autocmd!")
    for _, autocmd in ipairs(autocmds) do
        vim.cmd("autocmd " .. table.concat(autocmd, " "))
    end
    vim.cmd("augroup END")
end

return M
