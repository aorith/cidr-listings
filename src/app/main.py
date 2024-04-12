from pathlib import Path

from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.datastructures import ResponseHeader
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.middleware.base import DefineMiddleware
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from app.domain import routes
from app.domain.auth.middleware import JWTAuthenticationMiddleware
from app.lib.cli import CLIPlugin
from app.lib.db.base import get_dbmanager
from app.lib.db.migrations import run_migrations
from app.lib.default_admin_user import create_default_admin_user
from app.lib.exceptions import default_httpexception_handler
from app.lib.openapi import openapi_config
from app.lib.scheduled_tasks import Scheduler
from app.lib.settings import get_settings
from app.lib.worker import CidrWorker

settings = get_settings()
base_dir = Path(__file__).resolve().parent
templates_dir = base_dir / Path("domain/web/templates")

__version__ = settings.VERSION

auth_mw = DefineMiddleware(
    JWTAuthenticationMiddleware,
    exclude=[
        "^/docs",
        "^/static/",
        "^/favicon.ico$",
        "^/login",
        "^/v1/auth",
    ],
    exclude_http_methods=["OPTIONS"],
)

dbmngr = get_dbmanager()
cidr_worker = CidrWorker()
scheduler = Scheduler()


app = Litestar(
    debug=settings.DEBUG,
    openapi_config=openapi_config,
    route_handlers=[*routes, create_static_files_router(path="/", directories=["app/domain/web/statics"])],
    response_headers=[ResponseHeader(name="Vary", value="Accept-Encoding", description="Default vary header")],
    exception_handlers={HTTPException: default_httpexception_handler},
    plugins=[CLIPlugin()],
    middleware=[auth_mw],
    dependencies={"conn": Provide(dbmngr.get_connection)},
    on_startup=[dbmngr.setup, run_migrations, scheduler.run, create_default_admin_user],
    on_app_init=[],
    on_shutdown=[scheduler.stop, dbmngr.stop],
    template_config=TemplateConfig(directory=templates_dir, engine=JinjaTemplateEngine),
)
