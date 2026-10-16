# Keep the read-only image copy of the repo out of the jump list, so `z
# arch-ansible` lands on the ~/Projects checkout. Setting this replaces
# zoxide's default, so $HOME has to be re-added.
export _ZO_EXCLUDE_DIRS="$HOME:/usr/share/arch-ansible:/usr/share/arch-ansible/*"
eval "$(zoxide init zsh)"
