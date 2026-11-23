local opts = require("formatters")

-- Helm templates are Go templates, which prettier mangles
local function is_helm_template(ctx)
  local templates_dir = ctx.filename:match("^(.*)/templates/")
  return templates_dir ~= nil
    and vim.uv.fs_stat(templates_dir .. "/Chart.yaml") ~= nil
end

opts.formatters = {
  prettier = {
    condition = function(_, ctx)
      return not is_helm_template(ctx)
    end,
  },
  -- Run from the project root so ansible-lint finds the project's config
  ["ansible-lint"] = {
    cwd = require("conform.util").root_file({ ".ansible-lint", ".config/ansible-lint.yml", ".git" }),
  },
}

require("conform").setup(opts)
