#!/usr/bin/python

class FilterModule(object):
    def filters(self):
        return {
            "waybar_colored_block": self.waybar_colored_block
        }

    def waybar_colored_block(
        self,
        colorscheme_vars,
        left_color_base,
        color_base,
        text,
        first_block=False,
        last_block=False,
    ):
        if first_block:
            color = colorscheme_vars[color_base]
            return f'''<span color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text}</span>'''

        left_color = colorscheme_vars[left_color_base]
        color = colorscheme_vars[color_base]

        if last_block:
            return f'''<span background=\\"#{left_color}\\" color=\\"#{left_color}\\"></span><span background=\\"#{left_color}\\" color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text} </span>'''

        return f'''<span background=\\"#{left_color}\\" color=\\"#{left_color}\\"></span><span background=\\"#{left_color}\\" color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text}</span>'''
