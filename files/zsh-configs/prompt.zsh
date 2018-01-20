truncated_pwd() {
  echo '%(5~|%-1~/.../%3~|%4~)'
}

git_prompt() {
  prompt=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  branch_rc=$?

  if [ $branch_rc -eq 0 ] ; then
    git diff-index --quiet HEAD -- 2>&1 >/dev/null
    dirty_rc=$?

    if ! [ $dirty_rc -eq 0 ] ; then
      prompt="${prompt}%F{$bright_red}!%f"
    fi

    echo "%F{$purple}[$prompt%F{$purple}]%f "
  fi
}

setopt prompt_subst
export PROMPT='%F{$aqua}$(truncated_pwd)%f $(git_prompt)%F{$bright_yellow}>%F{$bright_green}>%F{$red}>%f '
