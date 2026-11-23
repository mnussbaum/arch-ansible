-- Diagnostics for the checks the repos' pre-commit hooks run that no language
-- server covers. Fixable findings are applied on save by conform instead.
local lint = require("lint")

local unit_suffixes = { "service", "socket", "timer", "mount", "target", "path" }

-- nvim only recognizes units under systemd directories, not ones kept
-- elsewhere, like an ansible role's files/
local unit_filetypes = {}
for _, suffix in ipairs(unit_suffixes) do
  unit_filetypes[suffix] = "systemd"
end
vim.filetype.add({ extension = unit_filetypes })

-- A unit's commands come from the system it ships in, not necessarily this
-- one, so missing binaries aren't reported.
local function parse_systemd_analyze(output, bufnr)
  local diagnostics = {}
  local filename = vim.api.nvim_buf_get_name(bufnr)

  for line in vim.gsplit(output, "\n", { trimempty = true }) do
    if not line:find("is not executable: No such file or directory", 1, true) then
      local lnum, message = line:match("^[^:]+:(%d+): (.+)$")
      if not lnum then
        message = line:gsub("^" .. vim.pesc(vim.fs.basename(filename)) .. ": ", "")
      end
      table.insert(diagnostics, {
        lnum = lnum and tonumber(lnum) - 1 or 0,
        col = 0,
        message = message,
        severity = vim.diagnostic.severity.WARN,
        source = "systemd-analyze",
      })
    end
  end

  return diagnostics
end

lint.linters.systemd_analyze = {
  cmd = "systemd-analyze",
  args = { "verify", "--man=no", "--recursive-errors=no" },
  stdin = false,
  append_fname = true,
  stream = "stderr",
  ignore_exitcode = true,
  parser = parse_systemd_analyze,
}

lint.linters_by_ft = {
  sh = { "shellcheck" },
  bash = { "shellcheck" },
  python = { "ruff" },
}

local function is_unit_file(bufnr)
  local suffix = vim.api.nvim_buf_get_name(bufnr):match("%.(%w+)$")

  return vim.bo[bufnr].filetype == "systemd" and vim.tbl_contains(unit_suffixes, suffix)
end

local function try_lint(args)
  lint.try_lint()

  if is_unit_file(args.buf) then
    lint.try_lint("systemd_analyze")
  end
end

vim.api.nvim_create_autocmd({ "BufReadPost", "BufWritePost" }, {
  group = vim.api.nvim_create_augroup("lint_setup", {}),
  callback = try_lint,
})
