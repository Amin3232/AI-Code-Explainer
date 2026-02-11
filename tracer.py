import sys
import copy
import types
from typing import Any


def _safe_repr(value: Any) -> dict:
    if value is None:
        return {"type": "NoneType", "value": None}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, (list, tuple)):
        type_name = type(value).__name__
        return {
            "type": type_name,
            "value": [_safe_repr(item) for item in value[:50]]
        }
    if isinstance(value, dict):
        safe_dict = {}
        for k, v in list(value.items())[:50]:
            safe_dict[str(k)] = _safe_repr(v)
        return {"type": "dict", "value": safe_dict}
    if isinstance(value, set):
        return {"type": "set", "value": [_safe_repr(item) for item in list(value)[:50]]}
    try:
        return {"type": type(value).__name__, "value": repr(value)}
    except Exception:
        return {"type": type(value).__name__, "value": "<unrepresentable>"}


def _is_traceable_var(name: str, value: Any) -> bool:
    if name.startswith("_"):
        return False
    if isinstance(value, (types.ModuleType, types.FunctionType, type)):
        return False
    return True


def _snapshot_locals(local_vars: dict) -> dict:
    return {
        name: _safe_repr(value)
        for name, value in local_vars.items()
        if _is_traceable_var(name, value)
    }


def _diff_variables(prev: dict, curr: dict) -> dict:
    changes = {"created": {}, "updated": {}, "deleted": {}}

    for name, val in curr.items():
        if name not in prev:
            changes["created"][name] = val
        elif prev[name] != val:
            changes["updated"][name] = {"from": prev[name], "to": val}

    for name in prev:
        if name not in curr:
            changes["deleted"][name] = prev[name]

    return changes


class ExecutionTracer:
    MAX_STEPS = 500

    def __init__(self, source_code: str):
        self.source_code = source_code
        self.source_lines = source_code.splitlines()
        self.steps: list[dict] = []
        self.prev_snapshot: dict = {}
        self.call_stack: list[str] = []

    def _get_source_line(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].rstrip()
        return ""

    def _trace_callback(self, frame, event, arg):
        if len(self.steps) >= self.MAX_STEPS:
            return None

        if frame.f_code.co_filename != "<user_code>":
            return self._trace_callback

        lineno = frame.f_lineno
        curr_snapshot = _snapshot_locals(frame.f_locals)
        var_changes = _diff_variables(self.prev_snapshot, curr_snapshot)

        step = {
            "step": len(self.steps) + 1,
            "event": event,
            "line_number": lineno,
            "source_line": self._get_source_line(lineno),
            "variables": curr_snapshot,
            "changes": var_changes,
        }

        if event == "call":
            func_name = frame.f_code.co_name
            self.call_stack.append(func_name)
            step["control_flow"] = {
                "type": "function_call",
                "function": func_name,
                "call_depth": len(self.call_stack),
            }
        elif event == "return":
            func_name = frame.f_code.co_name
            step["control_flow"] = {
                "type": "function_return",
                "function": func_name,
                "return_value": _safe_repr(arg),
            }
            if self.call_stack:
                self.call_stack.pop()
        elif event == "exception":
            exc_type, exc_value, _ = arg
            step["control_flow"] = {
                "type": "exception",
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_value),
            }
        elif event == "line":
            source = step["source_line"].strip()
            if source.startswith(("if ", "elif ")):
                step["control_flow"] = {"type": "conditional", "expression": source}
            elif source.startswith(("for ", "while ")):
                step["control_flow"] = {"type": "loop", "expression": source}
            elif source.startswith("return"):
                step["control_flow"] = {"type": "return_statement", "expression": source}

        self.steps.append(step)
        self.prev_snapshot = copy.deepcopy(curr_snapshot)
        return self._trace_callback

    def run(self, exec_globals: dict | None = None, compiled_code=None) -> dict:
        if compiled_code is not None:
            compiled = compiled_code
        else:
            compiled = compile(self.source_code, "<user_code>", "exec")

        if exec_globals is None:
            exec_globals = {"__builtins__": __builtins__}

        error = None
        completed = True

        old_trace = sys.gettrace()
        try:
            sys.settrace(self._trace_callback)
            exec(compiled, exec_globals)
        except Exception as e:
            error = {"type": type(e).__name__, "message": str(e)}
            completed = False
        finally:
            sys.settrace(old_trace)

        return {
            "source": self.source_code,
            "source_lines": self.source_lines,
            "steps": self.steps,
            "step_count": len(self.steps),
            "completed": completed,
            "error": error,
            "truncated": len(self.steps) >= self.MAX_STEPS,
        }
