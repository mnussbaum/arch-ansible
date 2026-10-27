# Working agreements

## Process

- For ticket or feature work, research first, then present a plan with its open
  questions. Don't write code until I've explicitly agreed to it.
- When driving a change with tests, show me the proposed tests before writing or
  running them.
- When I ask how to set up or run something, give me the commands. Don't run
  builds, servers or containers yourself unless I ask.
- Never post to GitHub (comments, review replies, reactions, resolving threads,
  PR descriptions) without my approval of the exact text. "Respond to" means
  draft a reply, not post it.

## Comments, commits and PRs

- Keep code comments short: what the code does or why. Leave out the incident
  that motivated it (hosts, error strings, dates) and people's names; state the
  rationale itself.
- Name branches `<TICKET>/mnussbaum/<kebab-description>`, with the ticket key in
  uppercase as written in the tracker.
- Commit subjects are `<TICKET>: <message>`.
- Use third-person verbs ("Adds", "Fixes"), not imperative, in subject and body.
- In repos not tracked with tickets the same rules apply with the ticket
  removed: `mnussbaum/<kebab-description>` and `Adds ...`.
- The commit body is a blank line then a short paragraph. Keep it high level
  and leave implementation detail to the code and PR description.
- Don't reword commits that are already pushed unless I ask.
- Commit messages explain why: the problem or constraint, not a list of
  mechanical edits that mirrors the diff. Tie design choices to their source.
  Skip plan phases, internal stage labels and discovery stories ("this failed in
  production"). Same for PR descriptions.
- Don't add a "Test plan" section to PR descriptions unless the repo's own
  instructions require one.

## Code style

- Separate a function's logical steps with blank lines: after early-return
  guards, between a computation and the step that uses it, and before the final
  return.
- Unit tests should cover every branch, but only through a module's external
  interface, not its private fields or helpers.
- Unit tests should always used fixed timestamps, never the current wall clock
  time

### Python

- Absolute imports only, never relative.
- Model records as `@dataclass(frozen=True, kw_only=True)`. Use `StrEnum` for
  categorical values; ints only for real quantities. Keep separate concerns in
  separate records joined by key rather than adding fields to existing ones.
- No functions defined inside other functions; lift helpers to module level
  with explicit parameters.
- For pipeline or tabular data, persist as Parquet and work in Polars with
  explicit schemas (`pl.Enum` mirroring `StrEnum`s), not JSON or Python loops.
  Projects use `uv`.

## Tools

- AWS: set `AWS_PROFILE=<profile>` on the command; don't use `assume`.
