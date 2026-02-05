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

            # Additional wait for dynamic content
            page.wait_for_timeout(2000)

            # Extract DOUGHCON level from rendered page
            doughcon_level = self._extract_doughcon_level(page)
            doughcon_label = self._extract_doughcon_label(page)

            # Extract store data using DOM
            stores = self._extract_stores_from_dom(page)

            # Extract Nothing Ever Happens Index status
            nehi_status = self._extract_nehi_status(page)

            logger.info(
                f"Extracted DOUGHCON level: {doughcon_level}, "
                f"Label: {doughcon_label}, NEHI: {nehi_status}, "
                f"Stores: {len(stores)}"
            )

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
        """Extract DOUGHCON level from the rendered page using DOM and text parsing."""
        try:
            # Method 1: Look for "DOUGHCON X" pattern in page text
            page_text = page.inner_text("body")
            
            # Pattern to match "DOUGHCON 4" or "DOUGHCON4" format
            match = re.search(r'DOUGHCON\s*(\d)', page_text, re.IGNORECASE)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 5:
                    logger.info(f"Found DOUGHCON level {level} via text pattern")
                    return level

            # Method 2: Try finding elements with specific text content
            # Look for elements that contain "DOUGHCON" followed by a number
            doughcon_elements = page.query_selector_all("h1, h2, h3, div, span, p")
            for el in doughcon_elements:
                try:
                    text = el.inner_text()
                    if "DOUGHCON" in text.upper():
                        match = re.search(r'DOUGHCON\s*(\d)', text, re.IGNORECASE)
                        if match:
                            level = int(match.group(1))
                            if 1 <= level <= 5:
                                logger.info(f"Found DOUGHCON level {level} via DOM element")
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

            # Known labels from the website (ordered by DOUGHCON level, 1-5)
            labels = [
                "MAXIMUM READINESS",              # Level 1
                "NEXT STEP TO MAXIMUM READINESS", # Level 2
                "INCREASE IN FORCE READINESS",    # Level 3
                "INCREASED INTELLIGENCE WATCH",   # Level 4 (also known as DOUBLE TAKE)
                "DOUBLE TAKE",                    # Level 4 alternate
                "LOWEST STATE OF READINESS",      # Level 5
            ]

            for label in labels:
                if label.upper() in page_text.upper():
                    logger.debug(f"Found DOUGHCON label: {label}")
                    return label

            return None

        except Exception as e:
            logger.debug(f"Error extracting DOUGHCON label: {e}")
            return None

    def _extract_nehi_status(self, page) -> str | None:
        """Extract Nothing Ever Happens Index status from the rendered page."""
        try:
            # Method 1: Look for "Status: <status>" pattern
            page_text = page.inner_text("body")
            
            # Known NEHI statuses
            nehi_statuses = [
                "IT HAPPENED",
                "SOMETHING IS HAPPENING",
                "SOMETHING MIGHT HAPPEN",
                "NOTHING EVER HAPPENS",
            ]

            # Try to find "Status: X" pattern first
            status_match = re.search(r'Status:\s*([A-Za-z\s]+?)(?:\n|$)', page_text)
            if status_match:
                found_status = status_match.group(1).strip()
                for status in nehi_statuses:
                    if status.upper() in found_status.upper():
                        logger.info(f"Found NEHI status via pattern: {status}")
                        return status

            # Fallback: search for known statuses in page text
            for status in nehi_statuses:
                if status.upper() in page_text.upper():
                    logger.info(f"Found NEHI status: {status}")
                    return status

            return None

        except Exception as e:
            logger.debug(f"Error extracting NEHI status: {e}")
            return None

    def _extract_stores_from_dom(self, page) -> list[PizzaStore]:
        """Extract store data from DOM structure."""
        stores = []

        try:
            # Find all store name elements (h3 tags with pizza store names)
            # Based on observed HTML: <h3 class="font-mono font-bold text-lg tracking-wider text-white">STORE NAME</h3>
            store_name_elements = page.query_selector_all(
                "h3.font-mono.font-bold"
            )
            
            logger.debug(f"Found {len(store_name_elements)} potential store name elements")

            for name_el in store_name_elements:
                try:
                    store_name = name_el.inner_text().strip()
                    
                    # Skip if not a pizza store (filter out non-store headers)
                    if not self._is_pizza_store_name(store_name):
                        continue

                    # Find the parent container to get status and distance
                    # Navigate up to find the store card container
                    parent = name_el.evaluate_handle(
                        "el => el.closest('div.bg-gray-900') || el.parentElement.parentElement.parentElement"
                    )
                    
                    status = "UNKNOWN"
                    distance = None
                    
                    if parent:
                        parent_text = parent.inner_text()
                        
                        # Extract status (OPEN, CLOSED, BUSY)
                        if "BUSY" in parent_text.upper():
                            status = "BUSY"
                        elif "OPEN" in parent_text.upper():
                            status = "OPEN"
                        elif "CLOSED" in parent_text.upper():
                            status = "CLOSED"
                        
                        # Extract distance (e.g., "1.4 mi")
                        distance_match = re.search(r'(\d+\.?\d*)\s*mi', parent_text)
                        if distance_match:
                            distance = f"{distance_match.group(1)} mi"

                    # Avoid duplicates
                    if not any(s.name.upper() == store_name.upper() for s in stores):
                        stores.append(PizzaStore(
                            name=store_name,
                            status=status,
                            distance=distance
                        ))
                        logger.debug(f"Found store: {store_name} - {status} - {distance}")

                except Exception as e:
                    logger.debug(f"Error processing store element: {e}")
                    continue

            # Fallback: if no stores found via DOM, try text-based extraction
            if not stores:
                logger.warning("No stores found via DOM, falling back to text extraction")
                stores = self._extract_stores_from_text(page)

            logger.info(f"Extracted {len(stores)} stores")

        except Exception as e:
            logger.error(f"Error extracting stores from DOM: {e}")

        return stores

    def _is_pizza_store_name(self, name: str) -> bool:
        """Check if the given name is likely a pizza store name."""
        name_upper = name.upper()
        
        # Known pizza store names
        known_stores = [
            "DOMINO'S PIZZA",
            "DOMINOS PIZZA",
            "EXTREME PIZZA",
            "DISTRICT PIZZA PALACE",
            "WE, THE PIZZA",
            "PIZZATO PIZZA",
            "PAPA JOHNS PIZZA",
            "PAPA JOHN'S PIZZA",
        ]
        
        # Check if it matches known stores
        for known in known_stores:
            if known in name_upper or name_upper in known:
                return True
        
        # Check if it contains "PIZZA" and looks like a store name
        if "PIZZA" in name_upper:
            # Exclude non-store text
            exclude_patterns = [
                'INDEX', 'HISTORY', 'INTELLIGENCE', 'THEORY', 'PENTAGON',
                'MAGAZINE', 'TIME', 'CRISIS', 'GULF', 'IRAN', 'LAUNCHES',
                'DELIVERED', 'CIA', 'DOCUMENTED', 'RUNNER', '→', '—',
                'REAL', 'ACCURATE', 'READ', 'DASHBOARD', 'CELEBRATED',
                'PIZZAS', 'VIRAL', 'FREQUENCIES', 'PETE-ZA', 'PIZZINT'
            ]
            if not any(word in name_upper for word in exclude_patterns):
                return True
        
        return False

    def _extract_stores_from_text(self, page) -> list[PizzaStore]:
        """Fallback: Extract store data from page text."""
        stores = []

        try:
            page_text = page.inner_text("body")
            lines = page_text.split('\n')

            # Known store names to look for
            known_stores = [
                "DOMINO'S PIZZA",
                "EXTREME PIZZA",
                "DISTRICT PIZZA PALACE",
                "WE, THE PIZZA",
                "PIZZATO PIZZA",
                "PAPA JOHNS PIZZA",
            ]

            for store_name in known_stores:
                # Find the store name in the text
                for i, line in enumerate(lines):
                    if store_name.upper() in line.upper():
                        status = "UNKNOWN"
                        distance = None
                        
                        # Look at surrounding lines for status and distance
                        for j in range(max(0, i-2), min(len(lines), i+5)):
                            check_line = lines[j].upper()
                            if "BUSY" in check_line:
                                status = "BUSY"
                            elif "OPEN" in check_line and status == "UNKNOWN":
                                status = "OPEN"
                            elif "CLOSED" in check_line and status == "UNKNOWN":
                                status = "CLOSED"
                            
                            # Look for distance
                            dist_match = re.search(r'(\d+\.?\d*)\s*mi', lines[j])
                            if dist_match:
                                distance = f"{dist_match.group(1)} mi"

                        # Avoid duplicates
                        if not any(s.name.upper() == store_name.upper() for s in stores):
                            stores.append(PizzaStore(
                                name=store_name,
                                status=status,
                                distance=distance
                            ))
                        break

        except Exception as e:
            logger.error(f"Error in text-based store extraction: {e}")

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
    print(f"NEHI Status: {data.nehi_status}")
    print(f"Stores: {len(data.stores)}")
    for store in data.stores:
        print(f"  - {store.name}: {store.status} ({store.distance})")
