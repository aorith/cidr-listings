from pathlib import Path

from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.datastructures import ResponseHeader
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.middleware.base import DefineMiddleware
from litestar.static_files.config import StaticFilesConfig
from litestar.template.config import TemplateConfig

from app.domain import routes
from app.domain.auth.middleware import JWTAuthenticationMiddleware
from app.lib.cli import CLIPlugin
from app.lib.db.base import get_dbmanager
from app.lib.db.migrations import run_migrations
from app.lib.exceptions import default_httpexception_handler
from app.lib.openapi import openapi_config
from app.lib.scheduled_tasks import Scheduler
from app.lib.settings import get_settings
from app.lib.worker import CidrWorker

settings = get_settings()
base_dir = Path(__file__).resolve().parent
statics_dir = base_dir / Path("domain/web/statics")
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
    route_handlers=routes,
    response_headers=[
        ResponseHeader(
            name="Vary", value=f"{settings.API_KEY_HEADER}, Accept-Encoding", description="Default vary header"
        )
    ],
    exception_handlers={HTTPException: default_httpexception_handler},
    plugins=[CLIPlugin()],
    middleware=[auth_mw],
    dependencies={"conn": Provide(dbmngr.get_connection)},
    on_startup=[dbmngr.setup, run_migrations, cidr_worker.run, scheduler.run],
    on_app_init=[],
    on_shutdown=[cidr_worker.stop, scheduler.stop, dbmngr.stop],
    static_files_config=[StaticFilesConfig(directories=[statics_dir], path="/", html_mode=False)],
    template_config=TemplateConfig(directory=templates_dir, engine=JinjaTemplateEngine),
)
