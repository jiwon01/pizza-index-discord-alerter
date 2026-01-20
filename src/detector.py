"""
Pizza Index Change Detector

Detects changes between current and previous pizza index states.
"""

import logging
from dataclasses import dataclass
from enum import Enum

from .scraper import PizzaData
from .state import StateManager

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts that can be triggered."""
    DOUGHCON_ESCALATION = "doughcon_escalation"
    DOUGHCON_DEESCALATION = "doughcon_deescalation"
    ORDER_SPIKE = "order_spike"
    STORE_BUSY = "store_busy"  # Store became busy or busy released
    NEHI_CHANGE = "nehi_change"  # Nothing Ever Happens Index changed


@dataclass
class Alert:
    """Represents a detected change that should trigger a notification."""
    alert_type: AlertType
    store_name: str | None = None
    previous_value: str | None = None
    current_value: str | None = None
    doughcon_level: int | None = None
    details: str | None = None

    @property
    def emoji(self) -> str:
        """Get the emoji for this alert type."""
        emojis = {
            AlertType.DOUGHCON_ESCALATION: "🚨",
            AlertType.DOUGHCON_DEESCALATION: "✅",
            AlertType.ORDER_SPIKE: "📈",
            AlertType.STORE_BUSY: "🔥",
            AlertType.NEHI_CHANGE: "🌍",
        }
        return emojis.get(self.alert_type, "⚠️")

    @property
    def title(self) -> str:
        """Get a human-readable title for this alert."""
        titles = {
            AlertType.DOUGHCON_ESCALATION: "DOUGHCON 레벨 상승!",
            AlertType.DOUGHCON_DEESCALATION: "DOUGHCON 레벨 하락",
            AlertType.ORDER_SPIKE: "주문 활동 급증 감지!",
            AlertType.STORE_BUSY: "매장 혼잡 상태 변경",
            AlertType.NEHI_CHANGE: "Nothing Ever Happens Index 변경",
        }
        return titles.get(self.alert_type, "알림")


class ChangeDetector:
    """Detects significant changes in pizza index data."""

    def __init__(
        self,
        state_manager: StateManager,
        spike_threshold_percent: float = 30.0
    ):
        self.state_manager = state_manager
        self.spike_threshold = spike_threshold_percent

    def detect_changes(self, current_data: PizzaData) -> list[Alert]:
        """
        Detect all changes between current and previous state.

        Returns a list of alerts for any significant changes detected.
        """
        alerts = []

        # Skip if this is the first run
        if self.state_manager.is_first_run():
            logger.info("First run - no previous state to compare")
            return alerts

        # Check DOUGHCON level changes
        doughcon_alert = self._check_doughcon_change(current_data)
        if doughcon_alert:
            alerts.append(doughcon_alert)

        # Check NEHI changes
        nehi_alert = self._check_nehi_change(current_data)
        if nehi_alert:
            alerts.append(nehi_alert)

        # Check store changes
        store_alerts = self._check_store_changes(current_data)
        alerts.extend(store_alerts)

        return alerts

    def _check_doughcon_change(self, current_data: PizzaData) -> Alert | None:
        """Check for DOUGHCON level changes."""
        previous_level = self.state_manager.get_previous_doughcon()
        current_level = current_data.doughcon_level

        if previous_level is None:
            return None

        if current_level < previous_level:
            # Lower number = higher alert (escalation)
            logger.warning(
                f"DOUGHCON ESCALATION: {previous_level} → {current_level}"
            )
            return Alert(
                alert_type=AlertType.DOUGHCON_ESCALATION,
                previous_value=str(previous_level),
                current_value=str(current_level),
                doughcon_level=current_level,
                details=f"위협 수준이 {previous_level}에서 {current_level}로 상승했습니다"
            )
        elif current_level > previous_level:
            # Higher number = lower alert (de-escalation)
            logger.info(
                f"DOUGHCON de-escalation: {previous_level} → {current_level}"
            )
            return Alert(
                alert_type=AlertType.DOUGHCON_DEESCALATION,
                previous_value=str(previous_level),
                current_value=str(current_level),
                doughcon_level=current_level,
                details=f"위협 수준이 {previous_level}에서 {current_level}로 하락했습니다"
            )

        return None

    def _check_nehi_change(self, current_data: PizzaData) -> Alert | None:
        """Check for Nothing Ever Happens Index changes."""
        previous_nehi = self.state_manager.get_previous_nehi_status()
        current_nehi = current_data.nehi_status

        if previous_nehi is None or current_nehi is None:
            return None

        if current_nehi.upper() != previous_nehi.upper():
            logger.info(
                f"NEHI change: {previous_nehi} → {current_nehi}"
            )
            return Alert(
                alert_type=AlertType.NEHI_CHANGE,
                previous_value=previous_nehi,
                current_value=current_nehi,
                doughcon_level=current_data.doughcon_level,
                details=f"Nothing Ever Happens Index가 '{previous_nehi}'에서 '{current_nehi}'로 변경되었습니다"
            )

        return None

    def _check_store_changes(self, current_data: PizzaData) -> list[Alert]:
        """Check for store BUSY status changes only."""
        alerts = []
        previous_stores = self.state_manager.get_previous_stores()

        for store in current_data.stores:
            if store.name not in previous_stores:
                # New store, skip comparison
                continue

            prev_store = previous_stores[store.name]
            prev_status = prev_store.get("status", "UNKNOWN")
            current_status = store.status

            # Only alert on BUSY-related changes:
            # 1. Any state -> BUSY (store became busy)
            # 2. BUSY -> Any other state (busy released)
            if prev_status != current_status:
                is_busy_change = (
                    current_status == "BUSY" or prev_status == "BUSY"
                )
                
                if is_busy_change:
                    if current_status == "BUSY":
                        detail_msg = f"{store.name}이(가) 혼잡 상태가 되었습니다"
                    else:
                        detail_msg = f"{store.name}의 혼잡 상태가 해제되었습니다 ({prev_status} → {current_status})"
                    
                    logger.info(
                        f"Store {store.name} BUSY change: {prev_status} → {current_status}"
                    )
                    alerts.append(Alert(
                        alert_type=AlertType.STORE_BUSY,
                        store_name=store.name,
                        previous_value=prev_status,
                        current_value=current_status,
                        doughcon_level=current_data.doughcon_level,
                        details=detail_msg
                    ))

            # Check activity spike (unchanged)
            prev_activity = prev_store.get("activity_percent")
            if store.activity_percent is not None and prev_activity is not None:
                increase = store.activity_percent - prev_activity
                if increase >= self.spike_threshold:
                    logger.info(
                        f"Store {store.name} activity spike: "
                        f"{prev_activity:.1f}% → {store.activity_percent:.1f}%"
                    )
                    alerts.append(Alert(
                        alert_type=AlertType.ORDER_SPIKE,
                        store_name=store.name,
                        previous_value=f"{prev_activity:.1f}%",
                        current_value=f"{store.activity_percent:.1f}%",
                        doughcon_level=current_data.doughcon_level,
                        details=(
                            f"{store.name} 활동량이 "
                            f"{increase:.1f}% 증가 ({prev_activity:.1f}% → {store.activity_percent:.1f}%)"
                        )
                    ))

        return alerts
