__all__ = ["configure"]


def configure(repl):
    """
    Configuration method. This is called during the start-up of ptpython.

    :param repl: `PythonRepl` instance.
    """
    repl.vi_mode = True

    # Ask for confirmation on exit.
    repl.confirm_exit = False

    repl.use_code_colorscheme("native")
    repl.color_depth = "DEPTH_24_BIT"  # True color.
