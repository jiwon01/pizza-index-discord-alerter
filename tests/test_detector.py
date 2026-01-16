"""
Tests for the change detector module.
"""

from unittest.mock import MagicMock

import pytest

from src.detector import Alert, AlertType, ChangeDetector
from src.scraper import PizzaData, PizzaStore
from src.state import StateManager


@pytest.fixture
def mock_state_manager():
    """Create a mock state manager."""
    manager = MagicMock(spec=StateManager)
    manager.is_first_run.return_value = False
    return manager


class TestChangeDetector:
    """Tests for ChangeDetector class."""

    def test_first_run_no_alerts(self, mock_state_manager):
        """First run should not generate any alerts."""
        mock_state_manager.is_first_run.return_value = True
        detector = ChangeDetector(mock_state_manager)

        data = PizzaData(doughcon_level=4, stores=[])
        alerts = detector.detect_changes(data)

        assert alerts == []

    def test_doughcon_escalation(self, mock_state_manager):
        """Detect DOUGHCON escalation (level decreases)."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {}
        detector = ChangeDetector(mock_state_manager)

        data = PizzaData(doughcon_level=2, stores=[])
        alerts = detector.detect_changes(data)

        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.DOUGHCON_ESCALATION
        assert alerts[0].previous_value == "4"
        assert alerts[0].current_value == "2"

    def test_doughcon_deescalation(self, mock_state_manager):
        """Detect DOUGHCON de-escalation (level increases)."""
        mock_state_manager.get_previous_doughcon.return_value = 2
        mock_state_manager.get_previous_stores.return_value = {}
        detector = ChangeDetector(mock_state_manager)

        data = PizzaData(doughcon_level=4, stores=[])
        alerts = detector.detect_changes(data)

        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.DOUGHCON_DEESCALATION

    def test_no_doughcon_change(self, mock_state_manager):
        """No alert when DOUGHCON level stays the same."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {}
        detector = ChangeDetector(mock_state_manager)

        data = PizzaData(doughcon_level=4, stores=[])
        alerts = detector.detect_changes(data)

        assert alerts == []

    def test_store_status_change(self, mock_state_manager):
        """Detect store status change."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {
            "DOMINO'S": {"name": "DOMINO'S", "status": "CLOSED", "activity_percent": None}
        }
        detector = ChangeDetector(mock_state_manager)

        data = PizzaData(
            doughcon_level=4,
            stores=[PizzaStore(name="DOMINO'S", status="OPEN")]
        )
        alerts = detector.detect_changes(data)

        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.STATUS_CHANGE
        assert alerts[0].store_name == "DOMINO'S"
        assert alerts[0].previous_value == "CLOSED"
        assert alerts[0].current_value == "OPEN"

    def test_order_spike(self, mock_state_manager):
        """Detect order activity spike."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {
            "PIZZA HUT": {"name": "PIZZA HUT", "status": "OPEN", "activity_percent": 30.0}
        }
        detector = ChangeDetector(mock_state_manager, spike_threshold_percent=25.0)

        data = PizzaData(
            doughcon_level=4,
            stores=[PizzaStore(name="PIZZA HUT", status="OPEN", activity_percent=60.0)]
        )
        alerts = detector.detect_changes(data)

        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.ORDER_SPIKE
        assert alerts[0].store_name == "PIZZA HUT"

    def test_order_spike_below_threshold(self, mock_state_manager):
        """No alert when activity increase is below threshold."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {
            "PIZZA HUT": {"name": "PIZZA HUT", "status": "OPEN", "activity_percent": 30.0}
        }
        detector = ChangeDetector(mock_state_manager, spike_threshold_percent=50.0)

        data = PizzaData(
            doughcon_level=4,
            stores=[PizzaStore(name="PIZZA HUT", status="OPEN", activity_percent=55.0)]
        )
        alerts = detector.detect_changes(data)

        assert alerts == []

    def test_multiple_alerts(self, mock_state_manager):
        """Detect multiple changes at once."""
        mock_state_manager.get_previous_doughcon.return_value = 4
        mock_state_manager.get_previous_stores.return_value = {
            "DOMINO'S": {"name": "DOMINO'S", "status": "CLOSED", "activity_percent": None},
            "PIZZA HUT": {"name": "PIZZA HUT", "status": "OPEN", "activity_percent": 20.0},
        }
        detector = ChangeDetector(mock_state_manager, spike_threshold_percent=30.0)

        data = PizzaData(
            doughcon_level=2,  # Escalation
            stores=[
                PizzaStore(name="DOMINO'S", status="OPEN"),  # Status change
                PizzaStore(name="PIZZA HUT", status="OPEN", activity_percent=60.0),  # Spike
            ]
        )
        alerts = detector.detect_changes(data)

        assert len(alerts) == 3
        alert_types = {a.alert_type for a in alerts}
        assert AlertType.DOUGHCON_ESCALATION in alert_types
        assert AlertType.STATUS_CHANGE in alert_types
        assert AlertType.ORDER_SPIKE in alert_types


class TestAlert:
    """Tests for Alert dataclass."""

    def test_emoji_mapping(self):
        """Test emoji property returns correct emoji."""
        alert = Alert(alert_type=AlertType.DOUGHCON_ESCALATION)
        assert alert.emoji == "🚨"

        alert = Alert(alert_type=AlertType.ORDER_SPIKE)
        assert alert.emoji == "📈"

        alert = Alert(alert_type=AlertType.STATUS_CHANGE)
        assert alert.emoji == "🔄"

    def test_title_mapping(self):
        """Test title property returns correct title."""
        alert = Alert(alert_type=AlertType.DOUGHCON_ESCALATION)
        assert "Increased" in alert.title

        alert = Alert(alert_type=AlertType.STATUS_CHANGE)
        assert "Status" in alert.title
