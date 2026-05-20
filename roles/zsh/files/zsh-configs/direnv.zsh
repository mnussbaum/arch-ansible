export DIRENV_LOG_FORMAT=""

if command -v direnv > /dev/null 2>&1 ; then
  eval "$(direnv hook zsh)"
fi
