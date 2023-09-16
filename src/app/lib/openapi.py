from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.spec import Components, Contact, License, SecurityScheme

from app.lib.settings import get_settings

settings = get_settings()

openapi_config = OpenAPIConfig(
    title=settings.OPENAPI_TITLE,
    version=settings.VERSION,
    contact=Contact(name=settings.OPENAPI_CONTACT_NAME, email=settings.OPENAPI_CONTACT_EMAIL),
    license=License(name="MIT", identifier="MIT"),
    use_handler_docstrings=True,
    root_schema_site="swagger",
    path=settings.OPENAPI_PATH,
    security=[{"BearerToken": []}],
    components=Components(
        security_schemes={
            "BearerToken": SecurityScheme(
                type="apiKey",
                name=settings.API_KEY_HEADER,
                security_scheme_in="header",
                description="API Key Header in the format `Bearer <TOKEN>`, "
                + "you must include the `Bearer` string along with the token",
            ),
            # "CookieToken": SecurityScheme( # this doesn't actually set the cookie in swagger
            # ),
        },
    ),
)
