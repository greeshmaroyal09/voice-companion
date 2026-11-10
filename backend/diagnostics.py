"""Safe per-request diagnostics shared by provider clients and HTTP routes."""
from contextvars import ContextVar


request_id_context: ContextVar[str] = ContextVar("voice_request_id", default="unassigned")


def current_request_id() -> str:
    return request_id_context.get()


def exception_chain(error: BaseException):
    """Flatten wrapped and grouped transport errors without reading their text."""
    stack = [error]
    seen: set[int] = set()
    while stack:
        cause = stack.pop(0)
        if id(cause) in seen:
            continue
        seen.add(id(cause))
        yield cause
        nested = list(getattr(cause, "exceptions", ()))
        if cause.__context__ is not None:
            nested.append(cause.__context__)
        if cause.__cause__ is not None:
            nested.append(cause.__cause__)
        stack.extend(nested)
