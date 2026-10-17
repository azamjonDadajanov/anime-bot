"""Messages a user sends to the administrators.

Both the website and the Telegram bot call :func:`send_support_message_sync`:
the text is stored once in ``SupportMessage`` and then forwarded to every
administrator through ``users.telegram_notify``.

Delivery is best effort, which is exactly why the row exists: a message that no
administrator received stays visible (``status = failed``) instead of being lost
with the failed HTTP call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from .models import SupportMessage
from .telegram_notify import notify_admins_user_message

logger = logging.getLogger(__name__)

# Long enough for a detailed problem report, short enough for one Telegram
# message once the header is prepended.
MAX_LENGTH = 2000
# One message a minute per account: the button is easy to press twice, and
# every message costs every administrator a notification.
MIN_SECONDS_BETWEEN_MESSAGES = 60

SENT = "sent"
FAILED = "failed"
TOO_SOON = "too_soon"
EMPTY = "empty"


@dataclass(frozen=True)
class SupportResult:
	"""Outcome of one send attempt."""

	status: str
	message: Optional[SupportMessage] = None
	delivered: bool = False
	retry_after: int = 0

	def __bool__(self) -> bool:
		return self.status == SENT


def send_support_message_sync(
	user,
	text: str,
	*,
	source: str = SupportMessage.Source.WEB,
	telegram_id: Optional[int] = None,
) -> SupportResult:
	"""Store ``text`` as a support message and forward it to the administrators."""
	body = (text or "").strip()
	if not body:
		return SupportResult(EMPTY)
	body = body[:MAX_LENGTH]

	now = timezone.now()
	previous = (
		SupportMessage.objects.filter(
			user=user,
			created_at__gte=now - timedelta(seconds=MIN_SECONDS_BETWEEN_MESSAGES),
		)
		.order_by("-created_at")
		.first()
	)
	if previous is not None:
		waited = int((now - previous.created_at).total_seconds())
		return SupportResult(
			TOO_SOON, retry_after=max(1, MIN_SECONDS_BETWEEN_MESSAGES - waited)
		)

	profile = getattr(user, "telegram_profile", None)
	message = SupportMessage.objects.create(
		user=user,
		telegram_id=telegram_id or (profile.telegram_id if profile is not None else None),
		text=body,
		source=source,
	)
	delivered, error = notify_admins_user_message(message)
	message.mark_delivered(delivered, error)
	if not delivered:
		logger.warning(
			"Support message %s from user %s was not delivered: %s",
			message.pk,
			user.pk,
			error or "unknown",
		)
	return SupportResult(
		SENT if delivered else FAILED, message=message, delivered=delivered
	)
