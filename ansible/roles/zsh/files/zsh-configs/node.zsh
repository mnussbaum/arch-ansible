# Switch node versions on cd from .node-version/.nvmrc; /usr/bin/node otherwise.
# env runs an initial `fnm use`, which logs "Bypassing fnm" on every new shell;
# quiet it, then restore info logging so cd still reports version switches.
eval "$(fnm env --use-on-cd --version-file-strategy=recursive --shell zsh --log-level=quiet)"
export FNM_LOGLEVEL=info
