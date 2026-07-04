"""Exception types and response validation for the Renpho API."""

from .constants import SUCCESS_CODES


class RenphoAPIError(Exception):
    """Raised when the Renpho API returns an error response."""

    def __init__(self, context: str, code, msg: str):
        self.context = context
        self.code = code
        self.msg = msg
        super().__init__(f"{context} failed: code={code}, msg={msg}")


def check_response(result: dict, context: str = "API call") -> None:
    """Raise :class:`RenphoAPIError` if the response indicates failure."""
    code = result.get("code")
    msg = result.get("msg", "")
    if msg.lower() == "success" or code in SUCCESS_CODES:
        return
    raise RenphoAPIError(context, code, msg)
