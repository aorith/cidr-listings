from app.lib.settings import get_settings
from litestar import MediaType, Request, Response
from litestar.datastructures import Cookie
from litestar.response import Redirect
from litestar.status_codes import (
    HTTP_204_NO_CONTENT,
    HTTP_307_TEMPORARY_REDIRECT,
    HTTP_401_UNAUTHORIZED,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

settings = get_settings()


def default_httpexception_handler(request: Request, exc: Exception) -> Response:
    """Handler for all exceptions subclassed from HTTPException."""  # noqa: D401
    status_code = getattr(exc, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)

    if request.url.path.startswith("/v1/"):
        preferred_type = MediaType.JSON
        extra = getattr(exc, "extra", "")
        content = {"status_code": status_code, "detail": getattr(exc, "detail", "")}
        if extra:
            content.update({"extra": extra})
    else:
        if not request.url.path.startswith("/login") and status_code == HTTP_401_UNAUTHORIZED:
            # redirect to login and reset the cookie
            if request.url.path.startswith("/parts"):
                return Response(
                    None,
                    status_code=HTTP_204_NO_CONTENT,  # htmx redirects need a 2xx
                    headers={"HX-Redirect": "/login"},
                    media_type=MediaType.HTML,
                    cookies=[Cookie(key=settings.API_KEY_COOKIE, value="", samesite="strict", max_age=-1)],
                )
            return Redirect(
                "/login",
                status_code=HTTP_307_TEMPORARY_REDIRECT,
                media_type=MediaType.HTML,
                cookies=[Cookie(key=settings.API_KEY_COOKIE, value="", samesite="strict", max_age=-1)],
            )

        preferred_type = MediaType.HTML
        detail = getattr(exc, "detail", "")  # litestar exceptions
        extras = getattr(exc, "extra", "")  # msgspec exceptions
        if extras and len(extras) >= 1:
            message = extras[0]
            if isinstance(message, dict):
                detail = f"{message.get('key', '')}: {message.get('message', detail)}"

        content = f"<p><span class='error'>{detail}</span></p>"

    return Response(
        media_type=preferred_type,
        content=content,
        headers={"HX-Trigger": "cleanErrors"},
        status_code=status_code,
    )
