def error(sodium, message: str, source: str = "<source>", content: str = "", position: int = 0, end: int = 1, kind: str = "syntax") -> None:
    color, reset, bold = sodium.THEME_COLOR, sodium.Color.reset, sodium.Color.bold
    if position < 0:
        position = 0
    if end < position:
        end = position + 1

    line_number = content.count("\n", 0, position) + 1
    line_start = content.rfind("\n", 0, position) + 1
    line_end = content.find("\n", position)
    if line_end < 0:
        line_end = len(content)
    line_text = content[line_start:line_end]
    column = position - line_start + 1
    highlight_start = max(0, position - line_start)
    highlight_end = min(len(line_text), max(highlight_start + 1, end - line_start))
    arrow_len = max(1, highlight_end - highlight_start)

    print(f"{color}sodium:{reset} {bold}{kind} error:{reset} {message}")
    print(f"  {color}--> {source}:{line_number}:{column}{reset}")
    if content:
        print(f" {line_number:>3} | {line_text}")
        print(f"     | {' ' * highlight_start}{color}{'^' * arrow_len}{reset}")
