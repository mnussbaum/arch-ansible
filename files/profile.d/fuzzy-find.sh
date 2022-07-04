# Fuzzy-find with ripgrep

export FZF_DEFAULT_COMMAND=$(cat <<-END
rg --files --no-ignore --hidden --follow --glob '!.git/' 2> /dev/null
END
)

export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND="cd ~/; bfs -type d -nohidden | sed s/^\./~/"
export FZF_COMPLETION_OPTS='+c -x'

_fzf_compgen_path() {
  rg --files "$1" | fzf-with-dir "$1"
}

_fzf_compgen_dir() {
  rg --files "$1" | fzf-only-dir "$1"
}
