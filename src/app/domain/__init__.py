from litestar.types import ControllerRouterHandler

from .auth.controllers import AuthAdminController, AuthController
from .cidr.controllers import CidrController
from .lists.controllers import ListController
from .web.controllers import WebController, WebPartCidrController, WebPartListController

routes: list[ControllerRouterHandler] = [
    CidrController,
    ListController,
    AuthController,
    AuthAdminController,
    WebController,
    WebPartListController,
    WebPartCidrController,
]
