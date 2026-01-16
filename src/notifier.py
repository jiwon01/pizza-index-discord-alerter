"""
Pizza Index Discord Notifier

Sends formatted Discord webhook notifications for pizza index alerts.
"""

import logging
from datetime import datetime, timezone

import httpx

from .detector import Alert
from .scraper import PizzaData

logger = logging.getLogger(__name__)

# Default DOUGHCON colors (can be overridden via config)
DEFAULT_DOUGHCON_COLORS = {
    1: 0xFF0000,  # Red - Critical
    2: 0xFF6600,  # Orange - High
    3: 0xFFCC00,  # Yellow - Elevated
    4: 0x0099FF,  # Blue - Guarded
    5: 0x00FF00,  # Green - Low
}


class DiscordNotifier:
    """Sends Discord webhook notifications for pizza alerts."""

    def __init__(
        self,
        webhook_url: str,
        doughcon_colors: dict[int, int] | None = None,
        doughcon_descriptions: dict[int, str] | None = None
    ):
        self.webhook_url = webhook_url
        self.colors = doughcon_colors or DEFAULT_DOUGHCON_COLORS
        self.descriptions = doughcon_descriptions or {}
        self.client = httpx.Client(timeout=30)

    def send_alert(self, alert: Alert, current_data: PizzaData) -> bool:
        """
        Send a single alert to Discord.

        Returns True if successful, False otherwise.
        """
        embed = self._build_embed(alert, current_data)

        payload = {
            "embeds": [embed]
        }

        try:
            response = self.client.post(self.webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Sent Discord alert: {alert.alert_type.value}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False

    def send_alerts(self, alerts: list[Alert], current_data: PizzaData) -> int:
        """
        Send multiple alerts to Discord.

        Returns the number of successfully sent alerts.
        """
        if not alerts:
            return 0

        success_count = 0

        # Group alerts into batches of up to 10 embeds (Discord limit)
        embeds = [self._build_embed(alert, current_data) for alert in alerts]

        for i in range(0, len(embeds), 10):
            batch = embeds[i:i+10]
            payload = {"embeds": batch}

            try:
                response = self.client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                success_count += len(batch)
                logger.info(f"Sent {len(batch)} Discord alerts")
            except httpx.HTTPError as e:
                logger.error(f"Failed to send Discord alerts batch: {e}")

        return success_count

    def _build_embed(self, alert: Alert, current_data: PizzaData) -> dict:
        """Build a Discord embed for an alert."""
        doughcon_level = alert.doughcon_level or current_data.doughcon_level
        color = self.colors.get(doughcon_level, 0x808080)

        # Build title with emoji
        title = f"{alert.emoji} {alert.title}"

        # Build description
        description = alert.details or ""

        # Build fields
        fields = []

        # Add change field
        if alert.previous_value and alert.current_value:
            fields.append({
                "name": "📊 변경 내용",
                "value": f"`{alert.previous_value}` → `{alert.current_value}`",
                "inline": True
            })

        # Add store name if applicable
        if alert.store_name:
            fields.append({
                "name": "🍕 매장",
                "value": alert.store_name,
                "inline": True
            })

        # Add current DOUGHCON level
        doughcon_desc = self.descriptions.get(
            doughcon_level,
            f"레벨 {doughcon_level}"
        )
        fields.append({
            "name": "🎯 현재 DOUGHCON",
            "value": f"**{doughcon_level}** - {doughcon_desc}",
            "inline": False
        })

        # Build embed
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Pizza Index Monitor 🍕"
            }
        }

        return embed

    def send_startup_notification(self, data: PizzaData) -> bool:
        """Send a startup status notification."""
        doughcon_level = data.doughcon_level
        color = self.colors.get(doughcon_level, 0x808080)
        doughcon_desc = self.descriptions.get(doughcon_level, f"레벨 {doughcon_level}")

        # Build store list
        stores_text = ""
        for store in data.stores[:5]:  # Show first 5 stores
            status_emoji = {
                "OPEN": "🟢",
                "CLOSED": "🔴",
                "BUSY": "🟡"
            }.get(store.status, "⚪")
            stores_text += f"{status_emoji} **{store.name}**: {store.status}\n"

        if len(data.stores) > 5:
            stores_text += f"_...외 {len(data.stores) - 5}개 매장_"

        embed = {
            "title": "🍕 Pizza Index Monitor 시작됨",
            "description": "피자 관련 지정학적 지표 모니터링을 시작합니다.",
            "color": color,
            "fields": [
                {
                    "name": "🎯 현재 DOUGHCON 레벨",
                    "value": f"**{doughcon_level}** - {doughcon_desc}",
                    "inline": False
                },
                {
                    "name": "🏪 활성 매장",
                    "value": stores_text or "감지된 매장 없음",
                    "inline": False
                }
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Pizza Index Monitor 🍕"
            }
        }

        try:
            response = self.client.post(self.webhook_url, json={"embeds": [embed]})
            response.raise_for_status()
            logger.info("Sent startup notification")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send startup notification: {e}")
            return False

    def send_test_alert(self) -> bool:
        """Send a test notification to verify webhook is working."""
        embed = {
            "title": "🔔 테스트 알림",
            "description": "Pizza Index Monitor 웹훅이 정상적으로 설정되었습니다!",
            "color": 0x00FF00,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Pizza Index Monitor 🍕"
            }
        }

        try:
            response = self.client.post(self.webhook_url, json={"embeds": [embed]})
            response.raise_for_status()
            logger.info("Test notification sent successfully")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send test notification: {e}")
            return False

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
