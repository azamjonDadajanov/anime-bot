"""Collapse the legacy tiered plans (free/plus/pro) into duration plans.

``plus`` and ``pro`` both meant "paid, 30 days" in practice, so they become the
``monthly`` plan and the expiry mirrors the old rule: 30 days from the moment
the subscription row was last written.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

LEGACY_MAPPING = {"plus": "monthly", "pro": "monthly"}


def forwards(apps, schema_editor):
	Subscription = apps.get_model("users", "Subscription")
	SubscriptionRequest = apps.get_model("users", "SubscriptionRequest")

	for subscription in Subscription.objects.all():
		plan = LEGACY_MAPPING.get(subscription.plan, subscription.plan)
		if plan == "free":
			continue
		subscription.plan = plan
		if subscription.expires_at is None:
			base = subscription.updated_at or timezone.now()
			subscription.started_at = base
			subscription.expires_at = base + timedelta(days=30)
		subscription.save(
			update_fields=["plan", "started_at", "expires_at", "updated_at"],
		)

	for request in SubscriptionRequest.objects.filter(plan__in=LEGACY_MAPPING):
		request.plan = LEGACY_MAPPING[request.plan]
		request.save(update_fields=["plan"])


def backwards(apps, schema_editor):
	Subscription = apps.get_model("users", "Subscription")
	Subscription.objects.filter(plan__in=["daily", "d15", "monthly", "quarterly", "yearly"]).update(
		plan="plus"
	)


class Migration(migrations.Migration):

	dependencies = [
		("users", "0009_subscription_expires_at_subscription_started_at_and_more"),
	]

	operations = [
		migrations.RunPython(forwards, backwards),
	]
