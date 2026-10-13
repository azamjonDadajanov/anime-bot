"""Administrator routers.

Two independent protections:

* ``AdminFilter`` routes only updates from ``ADMIN_IDS`` into this router, so
  everyone else falls through to the user handlers (which reply "not allowed").
* ``AdminGuardMiddleware`` is an *inner* middleware, so it runs only for updates
  that already matched an administrator handler. It is defence in depth: even if
  a filter were removed, the handler would never execute for a non-administrator.

The middleware is deliberately not an outer middleware: outer middlewares run
before the router filters and would swallow every ordinary user update.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from ...filters import AdminFilter
from ...middlewares.admin import AdminGuardMiddleware
from . import broadcast, channels, episodes, logs, media, panel, settings, subscriptions, users

admin_router = Router(name="admin")
admin_router.message.filter(F.chat.type == ChatType.PRIVATE, AdminFilter())
admin_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE, AdminFilter())

# Inner middlewares run after the filters, only for matching handlers.
admin_router.message.middleware(AdminGuardMiddleware())
admin_router.callback_query.middleware(AdminGuardMiddleware())

# `/admin` first, then the section routers.
admin_router.include_router(panel.router)
admin_router.include_router(media.router)
admin_router.include_router(episodes.router)
admin_router.include_router(channels.router)
admin_router.include_router(broadcast.router)
admin_router.include_router(users.router)
admin_router.include_router(subscriptions.router)
admin_router.include_router(settings.router)
admin_router.include_router(logs.router)

__all__ = ["admin_router"]
