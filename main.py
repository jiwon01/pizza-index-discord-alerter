#!/usr/bin/env python3
"""
Pizza Index Discord Alerter

Main entry point for the pizza index monitoring bot.
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from src.scraper import PizzaIndexScraper, PizzaData
from src.detector import ChangeDetector
from src.notifier import DiscordNotifier
from src.state import StateManager

# Load environment variables from .env file
load_dotenv()


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    
    if config_file.exists():
        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    # Allow environment variables to override config
    config["webhook_url"] = os.getenv("DISCORD_WEBHOOK_URL", config.get("webhook_url", ""))
    config["polling_interval_seconds"] = int(
        os.getenv("POLLING_INTERVAL", config.get("polling_interval_seconds", 300))
    )
    config["log_level"] = os.getenv("LOG_LEVEL", config.get("log_level", "INFO"))
    
    return config


def setup_logging(config: dict) -> None:
    """Configure logging based on config."""
    log_level = getattr(logging, config.get("log_level", "INFO").upper(), logging.INFO)
    log_format = config.get(
        "log_format",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


class PizzaMonitor:
    """Main pizza index monitoring class."""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        
        # Validate required config
        if not config.get("webhook_url"):
            raise ValueError(
                "Discord webhook URL is required. "
                "Set DISCORD_WEBHOOK_URL environment variable or add to config.yaml"
            )
        
        # Initialize components
        self.scraper = PizzaIndexScraper(
            url=config.get("target_url", "https://www.pizzint.watch/"),
            timeout=config.get("request_timeout_seconds", 30)
        )
        
        self.state_manager = StateManager(
            state_file=config.get("state_file", "state.json")
        )
        
        self.detector = ChangeDetector(
            state_manager=self.state_manager,
            spike_threshold_percent=config.get("order_spike_threshold_percent", 30)
        )
        
        self.notifier = DiscordNotifier(
            webhook_url=config["webhook_url"],
            doughcon_colors=config.get("doughcon_colors"),
            doughcon_descriptions=config.get("doughcon_descriptions")
        )
        
        self.polling_interval = config.get("polling_interval_seconds", 300)
    
    def run(self) -> None:
        """Start the monitoring loop."""
        self.running = True
        self.logger.info("Pizza Index Monitor starting...")
        self.logger.info(f"Polling interval: {self.polling_interval} seconds")
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        try:
            # Initial fetch
            data = self._fetch_data()
            if data:
                # Send startup notification
                if self.config.get("send_startup_notification", True):
                    self.notifier.send_startup_notification(data)
                
                # Save initial state
                self.state_manager.save_state(data)
                self.logger.info(
                    f"Initial state captured - DOUGHCON Level: {data.doughcon_level}, "
                    f"Stores: {len(data.stores)}"
                )
            
            # Main monitoring loop
            while self.running:
                self.logger.debug(f"Sleeping for {self.polling_interval} seconds...")
                time.sleep(self.polling_interval)
                
                if not self.running:
                    break
                
                self._check_for_updates()
        
        except Exception as e:
            self.logger.error(f"Fatal error in monitoring loop: {e}", exc_info=True)
            raise
        finally:
            self._cleanup()
    
    def _fetch_data(self) -> Optional[PizzaData]:
        """Fetch current pizza data."""
        try:
            data = self.scraper.fetch()
            self.logger.debug(
                f"Fetched data - DOUGHCON: {data.doughcon_level}, "
                f"Stores: {len(data.stores)}"
            )
            return data
        except Exception as e:
            self.logger.error(f"Failed to fetch pizza data: {e}")
            return None
    
    def _check_for_updates(self) -> None:
        """Check for updates and send alerts if needed."""
        data = self._fetch_data()
        if not data:
            return
        
        # Detect changes
        alerts = self.detector.detect_changes(data)
        
        if alerts:
            self.logger.info(f"Detected {len(alerts)} change(s), sending alerts...")
            sent = self.notifier.send_alerts(alerts, data)
            self.logger.info(f"Sent {sent}/{len(alerts)} alert(s)")
        else:
            self.logger.debug("No changes detected")
        
        # Save current state
        self.state_manager.save_state(data)
    
    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def _cleanup(self) -> None:
        """Clean up resources."""
        self.logger.info("Cleaning up...")
        self.scraper.close()
        self.notifier.close()
        self.logger.info("Goodbye! 🍕")


def main():
    """Main entry point."""
    # Load configuration
    config = load_config()
    
    # Setup logging
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("🍕 Pizza Index Discord Alerter")
    logger.info("=" * 50)
    
    # Handle test mode
    if "--test" in sys.argv:
        logger.info("Running in test mode...")
        notifier = DiscordNotifier(
            webhook_url=config["webhook_url"],
            doughcon_colors=config.get("doughcon_colors"),
            doughcon_descriptions=config.get("doughcon_descriptions")
        )
        success = notifier.send_test_alert()
        notifier.close()
        sys.exit(0 if success else 1)
    
    # Run monitor
    try:
        monitor = PizzaMonitor(config)
        monitor.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
