#!/usr/bin/python


class FilterModule(object):
    def filters(self):
        return {"waybar_colored_block": self.waybar_colored_block}

    def waybar_colored_block(
        self,
        color_scheme_vars,
        left_color_base,
        color_base,
        text,
        first_block=False,
        last_block=False,
        position=None,
    ):
        color = color_scheme_vars[color_base]

        if first_block and position == "right":
            return f"""<span color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text}</span>"""
        elif first_block and position == "left":
            return f"""<span background=\\"#{color}\\"> {text}</span>"""
        elif first_block:
            raise ValueError(
                f"""If last_block is True a position of 'left' or 'right' must be passed. Given: {position}"""
            )

        left_color = color_scheme_vars[left_color_base]

        if last_block and position == "left":
            return f"""<span background=\\"#{left_color}\\" color=\\"#{left_color}\\"></span><span background=\\"#{left_color}\\" color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text} </span><span color=\\"#{color}\\"></span>"""
        elif last_block and position == "right":
            return f"""<span background=\\"#{left_color}\\" color=\\"#{left_color}\\"></span><span background=\\"#{left_color}\\" color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text} </span>"""
        elif last_block:
            raise ValueError(
                f"""If last_block is True a position of 'left' or 'right' must be passed. Given: {position}"""
            )

        return f"""<span background=\\"#{left_color}\\" color=\\"#{left_color}\\"></span><span background=\\"#{left_color}\\" color=\\"#{color}\\"></span><span background=\\"#{color}\\"> {text}</span>"""
