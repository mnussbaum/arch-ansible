# Claude Code keeps its config, login and state in XDG_CONFIG_HOME, not ~/.claude
export CLAUDE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/claude"
