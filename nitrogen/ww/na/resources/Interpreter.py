from pathlib import Path


class Interpreter:
    def __init__(self, sodium, options: list[str]) -> None:
        self.sodium = sodium
        self.options = options
        self.scopes: list[dict] = []
        self.content = ""
        self.filename = "<source>"
        self.error_position = 0
        self.error_end = 1

    def run(self, tokens: list[list[dict]], content: str = "", filename: str = "<source>"):
        self.content = content
        self.filename = filename
        self.scopes = [self.builtins(), {}]
        value = self.lines(tokens)
        if isinstance(value, tuple) and value[0] == "return":
            return value[1]
        return 0

    def fail(self, token: dict | None, message: str, kind=RuntimeError):
        token = token or {}
        self.mark(token)
        raise kind(message)

    def mark(self, token: dict):
        if not token:
            return
        if "position" in token:
            self.error_position = token["position"]
            self.error_end = token.get("end", token["position"] + 1)
            return
        children = [child for child in token.get("children", []) if isinstance(child, dict)]
        if children:
            self.error_position = children[0].get("position", self.error_position)
            self.error_end = children[-1].get("end", self.error_position + 1)

    def builtins(self) -> dict:
        builtins = {
            "print": self._builtin_print,
            "input": self._builtin_input,
            "len": self._builtin_len,
            "range": self._builtin_range,
            "string": self._builtin_string,
            "number": self._builtin_number,
            "boolean": self._builtin_boolean,
            "array": self._builtin_array,
            "map": self._builtin_map,
            "set": self._builtin_set,
            "bytes": self._builtin_bytes,
            "import": self._builtin_import,
            "null": None,
            "function": {"kind": "function", "name": "function", "params": [], "body": [], "scope": []},
            "class": {"kind": "class", "name": "class", "methods": {}},
            "if": {"kind": "condition", "name": "if", "value": False},
            "unless": {"kind": "condition", "name": "unless", "value": False},
            "elseif": {"kind": "condition", "name": "elseif", "value": False},
            "else": {"kind": "condition", "name": "else", "value": False},
            "true": True,
            "false": False,
        }
        return builtins

    def _fmt_value(self, value, depth=0):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dict):
            if "__class__" in value and "kind" not in value:
                class_def = value["__class__"]
                name = class_def.get("name") if isinstance(class_def, dict) else "instance"
                return f"<instance {name}>"
            kind = value.get("kind")
            if kind == "function":
                name = value.get("name") or value.get("__name__") or "anonymous"
                return f"<function {name}>"
            if kind == "class":
                name = value.get("name") or value.get("__name__") or "anonymous"
                return f"<class {name}>"
            if kind == "condition":
                name = value.get("name") or value.get("__name__") or "anonymous"
                return f"<condition {name}>"
            if not value:
                return "{}"
            pieces = []
            for key, item in value.items():
                pieces.append(f"{self._fmt_value(key, depth + 1)}: {self._fmt_value(item, depth + 1)}")
            return "{" + ", ".join(pieces) + "}"
        if isinstance(value, list):
            if not value:
                return "[]"
            return "[" + ", ".join(self._fmt_value(item, depth + 1) for item in value) + "]"
        if isinstance(value, tuple):
            if not value:
                return "()"
            return "(" + ", ".join(self._fmt_value(item, depth + 1) for item in value) + ")"
        if isinstance(value, set):
            if not value:
                return "{}"
            return "{" + ", ".join(self._fmt_value(item, depth + 1) for item in sorted(value, key=lambda item: str(item))) + "}"
        return str(value)

    def _builtin_print(self, *values):
        print(*[self._fmt_value(value) for value in values])
        return None

    def _builtin_input(self, *values):
        prompt = "".join(str(value) for value in values)
        return input(prompt)

    def _builtin_len(self, value):
        return len(value)

    def _builtin_range(self, *values):
        return range(*values)

    def _builtin_string(self, value):
        return self._fmt_value(value)

    def _builtin_number(self, value):
        return float(value)

    def _builtin_boolean(self, value):
        return bool(value)

    def _builtin_array(self, *values):
        return list(values)

    def _builtin_map(self, *values):
        if not values:
            return {}
        if len(values) == 1 and isinstance(values[0], dict):
            return dict(values[0])
        return dict(values)

    def _builtin_set(self, *values):
        if not values:
            return set()
        if len(values) == 1 and isinstance(values[0], (list, tuple, set)):
            return set(values[0])
        return set(values)

    def _builtin_bytes(self, value):
        return bytes(value)

    def _builtin_import(self, name):
        return self.import_module(name)

    def import_module(self, module_name, token: dict | None = None):
        if isinstance(module_name, str):
            name = module_name.strip()
        else:
            name = str(module_name)
        if not name:
            self.fail(token, "import requires a module name", ImportError)
        if name.endswith(".na"):
            name = name[:-3]
        base_dir = Path(self.filename).resolve().parent if self.filename not in {"<source>", ""} else Path.cwd()
        path = (base_dir / name).with_suffix(".na")
        if not path.exists():
            path = (base_dir / f"{name}.na")
        if not path.exists():
            raise ImportError(f"cannot import {name!r}: module not found")
        source = path.read_text()
        tokenizer = self.sodium.res.Tokenizer(self.sodium, self.options)
        previous_filename = self.filename
        previous_scopes = list(self.scopes)
        module_interpreter = self.__class__(self.sodium, self.options)
        module_interpreter.filename = str(path)
        module_interpreter.content = source
        try:
            tokens = tokenizer.run(source)
            module_interpreter.scopes = [module_interpreter.builtins(), {}]
            module_result = module_interpreter.lines(tokens)
            if isinstance(module_result, tuple) and module_result[0] == "return":
                module_result = module_result[1]
            imported = module_interpreter.scopes[-1]
            if isinstance(imported, dict):
                self.scopes[-1].update(imported)
            return imported
        finally:
            self.filename = previous_filename
            self.scopes = previous_scopes

    def lines(self, lines: list[list[dict]]):
        result = None
        for line in lines:
            for token in line:
                result = self.value(token)
                if isinstance(result, tuple) and result[0] == "return":
                    return result
        return result

    def value(self, token: dict | None):
        if token is None:
            return None
        self.mark(token)
        kind = token["type"]
        value = token["value"]
        children = token.get("children", [])

        if kind in {"number", "string", "bytes", "literal"}:
            return value
        if kind == "identifier":
            return self.lookup(token)
        if kind == "array":
            return [self.value(child) for child in children]
        if kind == "set":
            return {self.value(child) for child in children}
        if kind == "map":
            result = {}
            for pair in children:
                key = self.value(pair["children"][0])
                result[key] = self.value(pair["children"][1])
            return result
        if kind == "custom":
            return {self.value(pair["children"][0]): self.value(pair["children"][1]) for pair in children}
        if kind == "member":
            return self.member(self.value(children[0]), value, token)
        if kind == "index":
            return self.index(self.value(children[0]), self.value(children[1]), token)
        if kind == "slice":
            obj = self.value(children[0])
            start = self.value(children[1]) if len(children) > 1 and children[1] is not None else None
            end = self.value(children[2]) if len(children) > 2 and children[2] is not None else None
            if start is None and end is None:
                return obj[:]
            if start is None:
                return obj[:end]
            if end is None:
                return obj[start:]
            return obj[start:end]
        if kind == "unary":
            operand = self.value(children[0])
            if value == "+":
                return +operand
            if value == "-":
                return -operand
            if value == "not":
                return not operand
            self.fail(token, f"unknown unary operator {value!r}", SyntaxError)
        if kind == "percent":
            return self.value(children[0]) / 100
        if kind == "operator":
            left = self.value(children[0])
            right = self.value(children[1])
            if value == "and":
                return left and right
            if value == "or":
                return left or right
            return self.binary(value, left, right, token)
        if kind == "assignment":
            result = self.value(children[1])
            self.assign(children[0], result)
            return result
        if kind == "call":
            return self.call(token)
        if kind == "handler":
            return self.handler(token)
        if kind == "import":
            return self.import_module(self.value(children[0]), token)
        if kind == "return":
            if children:
                return ("return", self.value(children[0]))
            return ("return", None)
        self.fail(token, f"unsupported token {kind!r}", SyntaxError)

    def lookup(self, token: dict):
        name = token["value"]
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.fail(token, f"undefined name {name!r}", NameError)

    def assign(self, target: dict, value):
        if target["type"] == "identifier":
            if isinstance(value, dict) and value.get("kind") in {"function", "class"}:
                value["name"] = target["value"]
            for scope in reversed(self.scopes):
                if target["value"] in scope:
                    scope[target["value"]] = value
                    return
            self.scopes[-1][target["value"]] = value
            return
        if target["type"] == "member":
            obj = self.value(target["children"][0])
            name = target["value"]
            if isinstance(obj, dict):
                obj[name] = value
                return
            setattr(obj, name, value)
            return
        if target["type"] == "index":
            obj = self.value(target["children"][0])
            key = self.value(target["children"][1])
            obj[key] = value
            return
        self.fail(target, "assignment target must be a name, member, or index", SyntaxError)

    def binary(self, operator: str, left, right, token: dict):
        try:
            if operator == "+":
                return left + right
            if operator == "-":
                return left - right
            if operator == "*":
                return left * right
            if operator == "/":
                return left / right
            if operator == "//":
                return left // right
            if operator == "%":
                return left % right
            if operator in {"^", "**"}:
                return left ** right
            if operator == "==":
                return left == right
            if operator == "!=":
                return left != right
            if operator == ">":
                return left > right
            if operator == "<":
                return left < right
            if operator == ">=":
                return left >= right
            if operator == "<=":
                return left <= right
            if operator == "in":
                return left in right
            if operator == "not in":
                return left not in right
            if operator == "is":
                return self.type_matches(left, right)
            if operator == "is not":
                return not self.type_matches(left, right)
        except (ArithmeticError, TypeError, ValueError) as error:
            self.fail(token, str(error), type(error))
        self.fail(token, f"unsupported operator {operator!r}", SyntaxError)

    def runtime_type(self, value):
        if value is True or value is False:
            return "boolean"
        if value is None:
            return "null"
        if isinstance(value, dict):
            if value.get("kind") == "function":
                return "function"
            if value.get("kind") == "class":
                return "class"
            if "__class__" in value:
                return "instance"
            return "map"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, set):
            return "set"
        return type(value).__name__

    def type_matches(self, left, right):
        left_kind = self.runtime_type(left)

        if right is None:
            return left_kind == "null"
        if right is True or right is False:
            return left_kind == "boolean"

        if isinstance(right, dict):
            if right.get("kind") == "function":
                return left_kind == "function"
            if right.get("kind") == "class":
                if left_kind == "class":
                    return True
                if left_kind == "instance":
                    return isinstance(left, dict) and left.get("__class__") is right
                return False
            return False

        if isinstance(right, str):
            return left_kind == right

        if callable(right):
            name = getattr(right, "__name__", "")
            if name.startswith("_builtin_"):
                name = name[len("_builtin_") :]
            if name in {"number", "string", "boolean", "array", "map", "set", "bytes", "function", "class", "null"}:
                if name == "class":
                    return left_kind == "class"
                if name == "function":
                    return left_kind == "function"
                return left_kind == name

        return False

    def member(self, obj, name: str, token: dict):
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
        self.fail(token, f"'{obj['name'] if 'name' in obj else obj['__class__']['name']}' has no member {name!r}", AttributeError)

    def index(self, obj, key, token: dict):
        try:
            return obj[key]
        except (IndexError, KeyError, TypeError) as error:
            self.fail(token, str(error), type(error))

    def call(self, token: dict):
        callee, *arguments = token["children"]
        target = self.value(callee)
        args = [self.value(arg) for arg in arguments]

        if isinstance(target, dict):
            kind = target.get("kind")
            if kind == "function":
                return self.invoke_function(target, args, token)
            if kind == "condition":
                if not args:
                    return target.get("value", False)
                return bool(args[0])
            if kind == "class":
                return self.instantiate_class(target, args, token)

        if callable(target):
            try:
                return target(*args)
            except (TypeError, ValueError, KeyError, IndexError, AttributeError) as error:
                self.fail(token, str(error), type(error))
        self.fail(callee, "value is not callable", TypeError)

    def invoke_function(self, func: dict, args: list, token: dict):
        params = list(func.get("params", []))
        body = list(func.get("body", []))
        if not body and not params and not args:
            return {"kind": "function", "params": [], "body": [], "scope": list(self.scopes)}
        if len(args) != len(params):
            self.fail(token, f"expected {len(params)} arguments, got {len(args)}", TypeError)
        previous = self.scopes
        self.scopes = list(func.get("scope", self.scopes)) + [dict(zip(params, args))]
        try:
            result = self.lines(body)
            if isinstance(result, tuple) and result[0] == "return":
                return result[1]
            return result
        finally:
            self.scopes = previous

    def instantiate_class(self, class_def: dict, args: list, token: dict):
        instance = {"__class__": class_def}
        for name, value in class_def.get("members", {}).items():
            instance[name] = value
        for name, method in class_def.get("methods", {}).items():
            instance[name] = method
        init = instance.get("init")
        if isinstance(init, dict) and init.get("kind") == "function":
            self.invoke_function(init, [instance, *args], token)
        elif "init" in instance and callable(instance["init"]):
            self.invoke_function(instance["init"], [instance, *args], token)
        elif args:
            self.fail(token, "class has no initializer", TypeError)
        return instance

    def handler(self, token: dict):
        target, *body = token["children"]

        if isinstance(target, dict) and target.get("type") == "call":
            callee = target.get("children", [None])[0]
            callee_name = callee.get("value") if isinstance(callee, dict) and callee.get("type") == "identifier" else None
            if callee_name == "function":
                params = [child["value"] for child in target.get("children", [])[1:] if isinstance(child, dict) and child.get("type") == "identifier"]
                return {"kind": "function", "name": None, "params": params, "body": body, "scope": list(self.scopes)}
            if callee_name == "class":
                class_def = {"kind": "class", "name": None, "methods": {}, "members": {}, "body": body, "scope": list(self.scopes)}
                scope = {}
                previous = self.scopes
                self.scopes = list(self.scopes) + [scope]
                try:
                    for line in body:
                        for statement in line:
                            result = self.value(statement)
                            if isinstance(statement, dict) and statement.get("type") == "assignment":
                                left = statement["children"][0]
                                if isinstance(left, dict) and left.get("type") == "identifier":
                                    name = left["value"]
                                    scope[name] = result
                                    class_def["members"][name] = result
                                    class_def[name] = result
                                    if isinstance(result, dict) and result.get("kind") in {"function", "class", "condition"}:
                                        class_def["methods"][name] = result
                    return class_def
                finally:
                    self.scopes = previous

        value = self.value(target)

        if isinstance(value, dict) and value.get("kind") == "function":
            value["body"] = body
            value["scope"] = list(self.scopes)
            return value

        if isinstance(value, dict) and value.get("kind") == "class":
            value["body"] = body
            value["scope"] = list(self.scopes)
            return value

        if isinstance(value, dict) and value.get("kind") == "condition":
            return self.lines(body) if bool(value.get("value", False)) else None

        if isinstance(value, bool):
            return self.lines(body) if value else None

        if callable(value):
            try:
                return value(self.lines(body))
            except TypeError as error:
                self.fail(token, str(error), type(error))

        return value

    def import_file(self, path: str):
        path = (Path(self.filename).parent / path).with_suffix(".na")
        try:
            source = path.read_text()
        except OSError as error:
            raise ImportError(f"cannot import {path}: {error.strerror}")
        tokenizer = self.sodium.res.Tokenizer(self.sodium, self.options)
        previous = self.filename
        self.filename = str(path)
        try:
            return self.lines(tokenizer.run(source))
        finally:
            self.filename = previous
