"""
Pizza Index State Manager

Handles persistence and comparison of pizza index state.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from .scraper import PizzaData

logger = logging.getLogger(__name__)


class StateManager:
    """Manages state persistence and comparison."""

    def __init__(self, state_file: str = "state.json"):
        self.state_file = Path(state_file)
        self._previous_state: dict | None = None
        self._load_state()

    def _load_state(self) -> None:
        """Load previous state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    self._previous_state = json.load(f)
                logger.info(f"Loaded previous state from {self.state_file}")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load state file: {e}")
                self._previous_state = None
        else:
            logger.info("No previous state file found, starting fresh")

    def save_state(self, data: PizzaData) -> None:
        """Save current state to file."""
        state = self._data_to_dict(data)
        state["last_updated"] = datetime.now().isoformat()

        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"Saved state to {self.state_file}")
            self._previous_state = state
        except OSError as e:
            logger.error(f"Failed to save state: {e}")

    def get_previous_state(self) -> dict | None:
        """Get the previous state if available."""
        return self._previous_state

    def get_previous_doughcon(self) -> int | None:
        """Get previous DOUGHCON level."""
        if self._previous_state:
            return self._previous_state.get("doughcon_level")
        return None

    def get_previous_stores(self) -> dict[str, dict]:
        """Get previous store states as a dict keyed by name."""
        if not self._previous_state:
            return {}

        stores = self._previous_state.get("stores", [])
        return {s["name"]: s for s in stores}

    def _data_to_dict(self, data: PizzaData) -> dict:
        """Convert PizzaData to a serializable dict."""
        return {
            "doughcon_level": data.doughcon_level,
            "doughcon_label": data.doughcon_label,
            "doughcon_description": data.doughcon_description,
            "stores": [
                {
                    "name": s.name,
                    "status": s.status,
                    "activity_percent": s.activity_percent,
                    "distance": s.distance
                }
                for s in data.stores
            ]
        }

    def is_first_run(self) -> bool:
        """Check if this is the first run (no previous state)."""
        return self._previous_state is None
