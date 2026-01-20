"""
Pizza Index Scraper Module

Fetches and parses data from the Pizza Index website using Playwright
for JavaScript rendering support.
"""

import logging
import re
from dataclasses import dataclass, field

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


@dataclass
class PizzaStore:
    """Represents a pizza store's current state."""
    name: str
    status: str  # OPEN, CLOSED, BUSY
    activity_percent: float | None = None  # Current activity level (0-100)
    distance: str | None = None


@dataclass
class PizzaData:
    """Complete pizza index data snapshot."""
    doughcon_level: int  # 1-5 (1 = highest alert)
    doughcon_label: str | None = None  # e.g., "DOUBLE TAKE"
    doughcon_description: str | None = None
    stores: list[PizzaStore] = field(default_factory=list)
    nehi_status: str | None = None  # Nothing Ever Happens Index status
    timestamp: str | None = None
    raw_data: dict | None = None  # For debugging


class PizzaIndexScraper:
    """Scrapes pizza index data from the website using Playwright."""

    def __init__(self, url: str = "https://www.pizzint.watch/", timeout: int = 30):
        self.url = url
        self.timeout = timeout * 1000  # Convert to milliseconds for Playwright
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)

    def fetch(self) -> PizzaData:
        """Fetch and parse the current pizza index data."""
        logger.info(f"Fetching data from {self.url}")

        self._ensure_browser()
        page = None

        try:
            page = self._browser.new_page()
            page.set_default_timeout(self.timeout)

            # Navigate to the page
            page.goto(self.url, wait_until="networkidle")

            # Wait for content to load - look for DOUGHCON text
            try:
                page.wait_for_selector("text=DOUGHCON", timeout=10000)
            except PlaywrightTimeout:
                logger.warning("Timeout waiting for DOUGHCON text, continuing anyway")

            # Extract DOUGHCON level from rendered page
            doughcon_level = self._extract_doughcon_level(page)
            doughcon_label = self._extract_doughcon_label(page)

            # Extract store data
            stores = self._extract_stores(page)

            # Extract Nothing Ever Happens Index status
            nehi_status = self._extract_nehi_status(page)

            logger.info(f"Extracted DOUGHCON level: {doughcon_level}, Label: {doughcon_label}, NEHI: {nehi_status}")

            return PizzaData(
                doughcon_level=doughcon_level,
                doughcon_label=doughcon_label,
                stores=stores,
                nehi_status=nehi_status
            )

        except Exception as e:
            logger.error(f"Error fetching pizza data: {e}")
            raise
        finally:
            if page:
                page.close()

    def _extract_doughcon_level(self, page) -> int:
        """Extract DOUGHCON level from the rendered page."""
        try:
            # Try to find text like "DOUGHCON 4" or "DOUGHCON 3"
            page_text = page.inner_text("body")

            # Pattern to match "DOUGHCON 4" format
            match = re.search(r'DOUGHCON\s*(\d)', page_text, re.IGNORECASE)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 5:
                    logger.info(f"Found DOUGHCON level {level} in page text")
                    return level

            # Try finding it in an element with specific selectors
            selectors = [
                '[class*="doughcon"]',
                '[class*="defcon"]',
                '[class*="level"]',
                '[class*="threat"]',
            ]

            for selector in selectors:
                try:
                    elements = page.query_selector_all(selector)
                    for el in elements:
                        text = el.inner_text()
                        match = re.search(r'(\d)', text)
                        if match:
                            level = int(match.group(1))
                            if 1 <= level <= 5:
                                logger.info(f"Found DOUGHCON level {level} in element: {selector}")
                                return level
                except Exception:
                    continue

            logger.warning("Could not find DOUGHCON level, defaulting to 5")
            return 5

        except Exception as e:
            logger.error(f"Error extracting DOUGHCON level: {e}")
            return 5

    def _extract_doughcon_label(self, page) -> str | None:
        """Extract DOUGHCON label (e.g., 'DOUBLE TAKE')."""
        try:
            page_text = page.inner_text("body")

            # Known labels from the website
            labels = [
                "MAXIMUM READINESS",
                "NEXT STEP TO MAXIMUM READINESS",
                "INCREASE IN FORCE READINESS",
                "INCREASED INTELLIGENCE WATCH",
                "DOUBLE TAKE",
                "LOWEST STATE OF READINESS",
            ]

            for label in labels:
                if label.upper() in page_text.upper():
                    return label

            return None

        except Exception as e:
            logger.debug(f"Error extracting DOUGHCON label: {e}")
            return None

    def _extract_nehi_status(self, page) -> str | None:
        """Extract Nothing Ever Happens Index status from the rendered page."""
        try:
            page_text = page.inner_text("body")

            # Known NEHI statuses
            nehi_statuses = [
                "IT HAPPENED",
                "SOMETHING IS HAPPENING",
                "SOMETHING MIGHT HAPPEN",
                "NOTHING EVER HAPPENS",
            ]

            # Look for "Status: <status>" pattern
            for status in nehi_statuses:
                if status.upper() in page_text.upper():
                    logger.info(f"Found NEHI status: {status}")
                    return status

            return None

        except Exception as e:
            logger.debug(f"Error extracting NEHI status: {e}")
            return None

    def _extract_stores(self, page) -> list[PizzaStore]:
        """Extract store data from the rendered page."""
        stores = []

        try:
            page_text = page.inner_text("body")
            lines = page_text.split('\n')

            # Pattern: store name (contains PIZZA or known names) followed by CLOSED/OPEN
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Skip lines that are too short or too long
                if len(line) < 5 or len(line) > 30:
                    i += 1
                    continue

                # Check if this line looks like a store name
                is_store = False
                if 'PIZZA' in line.upper():
                    # Must be a clean store name - exclude sentences and historical references
                    exclude_patterns = [
                        'INDEX', 'HISTORY', 'INTELLIGENCE', 'THEORY', 'PENTAGON',
                        'MAGAZINE', 'TIME', 'CRISIS', 'GULF', 'IRAN', 'LAUNCHES',
                        'DELIVERED', 'CIA', 'DOCUMENTED', 'RUNNER', '→', '—',
                        'REAL', 'ACCURATE', 'READ', 'DASHBOARD', 'CELEBRATED',
                        'PIZZAS', 'VIRAL'
                    ]
                    if not any(word in line.upper() for word in exclude_patterns):
                        is_store = True

                if is_store:
                    store_name = line.strip()
                    status = "UNKNOWN"

                    # Check next few lines for status
                    for j in range(1, 4):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip().upper()
                            if "CLOSED" in next_line:
                                status = "CLOSED"
                                break
                            elif "OPEN" in next_line:
                                status = "OPEN"
                                break
                            elif "BUSY" in next_line:
                                status = "BUSY"
                                break

                    # Avoid duplicates
                    if not any(s.name.upper() == store_name.upper() for s in stores):
                        stores.append(PizzaStore(name=store_name, status=status))
                        logger.debug(f"Found store: {store_name} - {status}")

                i += 1

            logger.info(f"Extracted {len(stores)} stores")

        except Exception as e:
            logger.error(f"Error extracting stores: {e}")

        return stores

    def close(self):
        """Close the browser and Playwright."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def fetch_pizza_data(url: str = "https://www.pizzint.watch/") -> PizzaData:
    """Convenience function to fetch pizza data."""
    with PizzaIndexScraper(url) as scraper:
        return scraper.fetch()


if __name__ == "__main__":
    # Test the scraper
    logging.basicConfig(level=logging.DEBUG)
    data = fetch_pizza_data()
    print(f"DOUGHCON Level: {data.doughcon_level}")
    print(f"DOUGHCON Label: {data.doughcon_label}")
    print(f"Stores: {len(data.stores)}")
    for store in data.stores:
        print(f"  - {store.name}: {store.status}")
