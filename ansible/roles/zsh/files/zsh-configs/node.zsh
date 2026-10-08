# Switch node versions on cd from .node-version/.nvmrc; /usr/bin/node otherwise.
eval "$(fnm env --use-on-cd --version-file-strategy=recursive --shell zsh)"
