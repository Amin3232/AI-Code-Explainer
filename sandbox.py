import signal
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Eval import (
    default_guarded_getattr,
    default_guarded_getitem,
    default_guarded_getiter,
)
from RestrictedPython.Guards import (
    guarded_unpack_sequence,
    safer_getattr,
)
from RestrictedPython import PrintCollector

from tracer import ExecutionTracer


class ExecutionTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise ExecutionTimeout("Code execution exceeded the time limit (5 seconds)")


def _restricted_import(name, *args, **kwargs):
    ALLOWED_MODULES = {"math", "string", "itertools", "functools", "collections", "decimal", "fractions", "statistics", "random"}
    if name in ALLOWED_MODULES:
        return __import__(name, *args, **kwargs)
    raise ImportError(f"Import of '{name}' is not allowed in the sandbox")


SAFE_BUILTINS = {
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "bytes": bytes,
    "bytearray": bytearray,
    "complex": complex,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "reversed": reversed,
    "sorted": sorted,
    "abs": abs,
    "max": max,
    "min": min,
    "sum": sum,
    "round": round,
    "pow": pow,
    "divmod": divmod,
    "len": len,
    "repr": repr,
    "chr": chr,
    "ord": ord,
    "format": format,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "type": type,
    "callable": callable,
    "hasattr": hasattr,
    "print": print,
    "any": any,
    "all": all,
    "hash": hash,
    "id": id,
    "iter": iter,
    "next": next,
    "hex": hex,
    "oct": oct,
    "bin": bin,
    "True": True,
    "False": False,
    "None": None,
    "__import__": _restricted_import,
}


def _build_restricted_globals() -> dict:
    import operator
    restricted = dict(safe_globals)
    restricted["__builtins__"] = SAFE_BUILTINS
    restricted["_getattr_"] = default_guarded_getattr
    restricted["_getitem_"] = default_guarded_getitem
    restricted["_getiter_"] = default_guarded_getiter
    restricted["_unpack_sequence_"] = guarded_unpack_sequence
    restricted["_iter_unpack_sequence_"] = guarded_unpack_sequence
    restricted["_write_"] = lambda obj: obj
    _inplace_ops = {
        '+=': operator.iadd,
        '-=': operator.isub,
        '*=': operator.imul,
        '/=': operator.itruediv,
        '//=': operator.ifloordiv,
        '%=': operator.imod,
        '**=': operator.ipow,
        '<<=': operator.ilshift,
        '>>=': operator.irshift,
        '&=': operator.iand,
        '|=': operator.ior,
        '^=': operator.ixor,
    }
    restricted["_inplacevar_"] = lambda op, x, y: _inplace_ops[op](x, y)
    restricted["_print_"] = PrintCollector
    restricted["_getiter_"] = default_guarded_getiter
    return restricted


def validate_code(source: str) -> tuple[object | None, dict | None]:
    try:
        compiled = compile_restricted(source, "<user_code>", "exec")
        return compiled, None
    except SyntaxError as e:
        return None, {
            "type": "SyntaxError",
            "message": str(e),
        }


def execute_sandboxed(source: str, timeout: int = 5) -> dict:
    compiled, validation_error = validate_code(source)
    if validation_error:
        return {
            "source": source,
            "source_lines": source.splitlines(),
            "steps": [],
            "step_count": 0,
            "completed": False,
            "error": validation_error,
            "truncated": False,
        }

    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
    except (OSError, AttributeError, ValueError):
        pass

    try:
        exec_globals = _build_restricted_globals()
        tracer = ExecutionTracer(source)
        result = tracer.run(exec_globals=exec_globals, compiled_code=compiled)
        return result
    except ExecutionTimeout as e:
        return {
            "source": source,
            "steps": [],
            "step_count": 0,
            "completed": False,
            "error": {"type": "TimeoutError", "message": str(e)},
            "truncated": False,
        }
    except Exception as e:
        return {
            "source": source,
            "steps": [],
            "step_count": 0,
            "completed": False,
            "error": {"type": type(e).__name__, "message": str(e)},
            "truncated": False,
        }
    finally:
        try:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        except (OSError, AttributeError, ValueError):
            pass
