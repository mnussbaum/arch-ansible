export SPACESHIP_CHAR_SYMBOL="%{\e[38;5;001m%}•%{\e[38;5;011m%}•%{\e[38;5;004m%}• "
# Yields three bullets, colored red, yellow and blue

export SPACESHIP_EXIT_CODE_SHOW="true"
export SPACESHIP_VI_MODE_SHOW="false"

autoload -U promptinit; promptinit
prompt spaceship
