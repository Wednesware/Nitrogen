from nitrogen import require
Color = require("magnesium.color").Color
FilePath = require("magnesium.filepath").FilePath


def run(sodium, args, options) -> None:
    tokenizer: sodium.res.Tokenizer = sodium.res.Tokenizer(sodium, options)
    interpreter: sodium.res.Interpreter = sodium.res.Interpreter(sodium, options)
    source = "<source>"
    try:
        source = args[0].strip()
        sodium.content = FilePath(source).read()
    except FileNotFoundError:
        print(f"{sodium.THEME_COLOR}sodium:{Color.reset} file not found: {args[0].strip()}")
        raise SystemExit(1)
    except IndexError:
        print(f"{sodium.THEME_COLOR}sodium:{Color.reset} no file specified")
        raise SystemExit(1)
    try:
        tokens: list[list[dict]] = tokenizer.run(sodium.content)
        if "no-exec" in options:
            return
        exit(interpreter.run(tokens, sodium.content, source))
    except Exception as exception:
        owner = interpreter if interpreter.content else tokenizer
        sodium.script.error(str(exception) or exception.__class__.__name__, source, getattr(sodium, "content", ""), owner.error_position, owner.error_end, "syntax" if isinstance(exception, SyntaxError) else "name" if isinstance(exception, NameError) else "runtime")
        raise SystemExit(1)