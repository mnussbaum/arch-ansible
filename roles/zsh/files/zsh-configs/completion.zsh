zmodload zsh/complist
autoload -Uz compinit
compinit

zstyle :compinstall filename '${HOME}/.zshrc'
zstyle ':completion:*:default' list-colors ${(s.:.)LS_COLORS}
