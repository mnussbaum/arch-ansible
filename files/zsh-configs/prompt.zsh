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
      prompt="${prompt}!"
    fi

    echo " [$prompt]"
  fi
}


setopt prompt_subst
export PROMPT='$(truncated_pwd)$(git_prompt): '
