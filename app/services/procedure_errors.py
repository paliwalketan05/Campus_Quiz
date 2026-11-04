from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError


def translate_procedure_error(exc: DBAPIError) -> HTTPException | None:
    original = exc.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate != "P0001":
        return None

    message = str(original).lower()
    if "authentication failed" in message:
        return HTTPException(status_code=401, detail="Actor authentication is no longer valid")
    if "unauthorized" in message or "authorization failed" in message:
        return HTTPException(status_code=403, detail="Not authorized to perform this operation")
    if "does not exist" in message or "not found" in message:
        return HTTPException(status_code=404, detail="Requested quiz or attempt was not found")
    if any(
        phrase in message
        for phrase in (
            "not actively enrolled",
            "does not have a registered student profile",
            "does not possess required role",
        )
    ):
        return HTTPException(status_code=403, detail="Not eligible to perform this operation")
    return HTTPException(
        status_code=409,
        detail="The operation is not valid for the current attempt or session state",
    )
