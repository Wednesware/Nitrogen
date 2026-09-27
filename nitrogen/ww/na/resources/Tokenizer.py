import json
import re


class Tokenizer:
    def __init__(self, sodium, options: list[str]) -> None:
        self.sodium = sodium
        self.options = options
        self.tokens: list[dict] = []
        self.index = 0
        self.content: str | None = None
        self.error_position = 0
        self.error_end = 1
        self.closers: list[str] = []

    def token(self, kind: str, value=None, children=None, position=None, end=None) -> dict:
        item = {"type": kind, "value": value, "children": children or []}
        if position is not None:
            item["position"] = position
            item["end"] = end if end is not None else position + 1
        return item

    def run(self, content: str) -> list[list[dict]]:
        self.content = content
        self.tokens = self.lex(content)
        self.index = 0
        parsed = self.lines()
        if "show-tokens" in self.options:
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        return parsed

    def lex(self, content: str) -> list[dict]:
        tokens: list[dict] = []
        index = 0
        while index < len(content):
            char = content[index]
            if char in " \t\r":
                index += 1
            elif char == "#":
                newline = content.find("\n", index)
                if newline < 0:
                    break
                index = newline + 1
            elif char in {"\n", ";"}:
                tokens.append(self.token("newline", char, position=index, end=index + 1))
                index += 1
            elif char in {'"', "'"}:
                start = index
                value, index = self.string(content, index)
                tokens.append(self.token("string", value, position=start, end=index))
            elif char == "b" and index + 1 < len(content) and content[index + 1] in {'"', "'"}:
                start = index
                value, index = self.string(content, index + 1)
                tokens.append(self.token("bytes", value.encode(), position=start, end=index))
            elif char.isdigit() or (char == "." and index + 1 < len(content) and content[index + 1].isdigit()):
                start = index
                match = re.match(r"(?:\d+\.?\d*|\.\d)(?:[eE][+-]?\d+)?", content[index:])
                if match is None:
                    raise SyntaxError(f"invalid number at index {index}")
                value = match.group()
                number_index = index + len(value)
                value_token = float(value) if any(item in value for item in ".eE") else int(value)
                if number_index < len(content) and content[number_index] == "%":
                    next_char = content[number_index + 1] if number_index + 1 < len(content) else ""
                    if next_char.isdigit() or next_char == ".":
                        index = number_index
                        tokens.append(self.token("number", value_token, position=start, end=index))
                        continue
                    index = number_index + 1
                    tokens.append(self.token("number", value_token / 100, position=start, end=index))
                    continue
                index = number_index
                tokens.append(self.token("number", value_token, position=start, end=index))
            elif char.isalpha() or char == "_":
                start = index
                match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", content[index:])
                if match is None:
                    raise SyntaxError(f"invalid identifier at index {index}")
                value = match.group()
                index += len(value)
                if value in {"true", "false", "null"}:
                    tokens.append(self.token("literal", {"true": True, "false": False, "null": None}[value], position=start, end=index))
                else:
                    tokens.append(self.token("identifier", value, position=start, end=index))
            else:
                start = index
                op = next((operator for operator in ("==", "!=", ">=", "<=", "**", "//") if content.startswith(operator, index)), char)
                index += len(op)
                tokens.append(self.token("symbol", op, position=start, end=index))
        tokens.append(self.token("eof", position=len(content), end=len(content)))
        return tokens

    def string(self, content: str, index: int) -> tuple[str, int]:
        quote = content[index]
        index += 1
        value = ""
        while index < len(content):
            char = content[index]
            if char == "\\" and index + 1 < len(content):
                index += 1
                escaped = content[index]
                value += {"n": "\n", "t": "\t", "r": "\r"}.get(escaped, escaped)
                index += 1
            elif char == quote:
                return value, index + 1
            else:
                value += char
                index += 1
        self.error_position = index
        self.error_end = index + 1
        raise SyntaxError("unterminated string literal")

    def peek(self, value=None) -> dict:
        token = self.tokens[self.index]
        self.error_position = token.get("position", self.error_position)
        self.error_end = token.get("end", self.error_position + 1)
        return token if value is None else token["value"] == value

    def take(self, value=None) -> dict:
        token = self.peek()
        if value is not None and token["value"] != value:
            raise SyntaxError(f"expected {value!r}, got {token['value']!r}")
        self.index += 1
        return token

    def lines(self, stop=None) -> list[list[dict]]:
        lines: list[list[dict]] = []
        while self.peek()["type"] != "eof" and (stop is None or self.peek()["value"] != stop):
            if self.peek()["type"] == "newline":
                self.take()
                continue
            line: list[dict] = []
            while True:
                current = self.peek()
                if current["type"] == "eof" or (stop is not None and current["value"] == stop):
                    break
                if current["type"] == "newline" or current["value"] == ";":
                    self.take()
                    break
                line.append(self.statement())
            if line:
                lines.append(line)
        return lines

    def statement(self) -> dict:
        if self.peek()["type"] == "identifier" and self.peek()["value"] == "return":
            self.take()
            if self.peek()["type"] == "newline" or self.peek()["value"] == ";" or self.peek()["value"] == "}" or self.peek()["type"] == "eof":
                return self.token("return")
            return self.token("return", children=[self.expression()])
        if self.peek()["type"] == "identifier" and self.peek()["value"] == "import":
            self.take()
            if self.peek()["type"] in {"newline", "eof"} or self.peek()["value"] == "}":
                raise SyntaxError("import requires a module name")
            return self.token("import", children=[self.expression()])
        return self.expression()

    def expression(self, minimum=0) -> dict:
        left = self.prefix()
        while True:
            if self.peek()["value"] == "%" and not self.is_modulo_operator():
                self.take()
                left = self.token("percent", children=[left])
                continue
            current = self.peek()
            if current["type"] == "eof" or current["value"] in self.closers or current["type"] == "newline" or current["value"] == ";":
                break
            operator = self.operator()
            if operator is None or self.precedence(operator) < minimum:
                break
            self.take()
            if operator in {"not in", "is not"}:
                self.take()
            right = self.expression(self.precedence(operator) + 1)
            left = self.token("assignment" if operator == "=" else "operator", operator, [left, right])
        return left

    def is_modulo_operator(self) -> bool:
        if self.peek()["value"] != "%":
            return False
        index = self.index + 1
        if index >= len(self.tokens):
            return False
        next_token = self.tokens[index]
        return next_token.get("type") == "number"

    def precedence(self, operator: str) -> int:
        table = {
            "=": 1,
            "or": 2,
            "and": 3,
            "==": 4,
            "!=": 4,
            ">": 4,
            "<": 4,
            ">=": 4,
            "<=": 4,
            "in": 4,
            "is": 4,
            "not in": 4,
            "is not": 4,
            "+": 5,
            "-": 5,
            "*": 6,
            "/": 6,
            "//": 6,
            "%": 6,
            "**": 7,
            "^": 7,
        }
        return table.get(operator, -1)

    def operator(self):
        current = self.peek()
        if current["type"] == "identifier":
            word = current["value"]
            if word == "not" and self.tokens[self.index + 1]["value"] in {"in", "is"}:
                return f"not {self.tokens[self.index + 1]['value']}"
            if word == "is" and self.tokens[self.index + 1]["value"] == "not":
                return "is not"
            if word in {"and", "or", "in", "is", "not"}:
                return word
            return None
        value = current["value"]
        if value in {"==", "!=", ">=", "<=", "+", "-", "*", "/", "//", "%", "**", "^", "=", ">", "<"}:
            return value
        return None

    def prefix(self) -> dict:
        current = self.peek()
        if current["value"] in {"+", "-"} or (current["type"] == "identifier" and current["value"] == "not"):
            operator = self.take()["value"]
            return self.token("unary", operator, [self.prefix()])
        node = self.atom()
        while True:
            if self.peek("("):
                node = self.token("call", children=[node, *self.items("(", ")")])
            elif self.peek("["):
                self.take("[")
                start = None if self.peek(":") else self.expression()
                if self.peek(":"):
                    self.take(":")
                    end = None if self.peek("]") else self.expression()
                    self.take("]")
                    node = self.token("slice", children=[node, start, end])
                else:
                    self.take("]")
                    node = self.token("index", children=[node, start])
            elif self.peek("."):
                self.take(".")
                attribute = self.take()
                if attribute["type"] != "identifier":
                    raise SyntaxError("expected property name")
                node = self.token("member", attribute["value"], [node])
            elif self.peek("{"):
                self.take("{")
                node = self.token("handler", children=[node, *self.lines("}")])
                self.take("}")
            else:
                return node

    def atom(self) -> dict:
        token = self.take()
        if token["type"] in {"string", "number", "bytes", "literal", "identifier"}:
            return token
        if token["value"] == "(":
            inner = self.expression()
            self.take(")")
            return inner
        if token["value"] == "[":
            return self.token("array", children=self.items_open("]"))
        if token["value"] == "{":
            return self.collection("}")
        if token["value"] == "<":
            return self.token("custom", children=self.pairs(">"))
        raise SyntaxError(f"unexpected {token['value']!r}")

    def items(self, opening: str, closing: str) -> list[dict]:
        self.take(opening)
        return self.items_open(closing)

    def items_open(self, closing: str) -> list[dict]:
        values: list[dict] = []
        while not self.peek(closing):
            values.append(self.expression())
            if not self.peek(","):
                break
            self.take(",")
        self.take(closing)
        return values

    def collection(self, closing: str) -> dict:
        if self.peek(closing):
            self.take(closing)
            return self.token("map")
        index = self.index
        first = self.expression()
        if self.peek(":"):
            self.index = index
            return self.token("map", children=self.pairs(closing))
        values = [first]
        while self.peek(","):
            self.take(",")
            values.append(self.expression())
        self.take(closing)
        return self.token("set", children=values)

    def pairs(self, closing: str) -> list[dict]:
        pairs: list[dict] = []
        self.closers.append(closing)
        try:
            while not self.peek(closing):
                key = self.expression()
                self.take(":")
                pairs.append(self.token("pair", children=[key, self.expression()]))
                if not self.peek(","):
                    break
                self.take(",")
            self.take(closing)
        finally:
            self.closers.pop()
        return pairs

    def returned(self, value=None) -> dict:
        return self.token("return", children=[] if value is None else [value])
