export BASE16_SHELL=/usr/share/zsh/plugins/base16-shell
eval "$($BASE16_SHELL/profile_helper.sh)"
base16_default-dark

autoload -U colors zsh/terminfo
colors

export black="000"
export red="001"
export green="002"
export yellow="003"
export blue="004"
export purple="005"
export aqua="006"
export gray="007"
export orange="166"
export bright_red="124"
export bright_green="106"
export bright_yellow="172"
export bright_blue="066"
export bright_purple="132"
export bright_aqua="072"

eval "$(dircolors <(envsubst < ~/.config/dircolors))"
