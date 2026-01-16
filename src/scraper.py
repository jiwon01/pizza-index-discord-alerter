"""
Pizza Index Scraper Module

Fetches and parses data from the Pizza Index website.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class PizzaStore:
    """Represents a pizza store's current state."""
    name: str
    status: str  # OPEN, CLOSED, BUSY
    activity_percent: Optional[float] = None  # Current activity level (0-100)
    distance: Optional[str] = None


@dataclass
class PizzaData:
    """Complete pizza index data snapshot."""
    doughcon_level: int  # 1-5 (1 = highest alert)
    doughcon_label: Optional[str] = None  # e.g., "DOUBLE TAKE"
    doughcon_description: Optional[str] = None
    stores: list[PizzaStore] = field(default_factory=list)
    timestamp: Optional[str] = None
    raw_data: Optional[dict] = None  # For debugging


class PizzaIndexScraper:
    """Scrapes pizza index data from the website."""
    
    def __init__(self, url: str = "https://www.pizzint.watch/", timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            },
            follow_redirects=True
        )
    
    def fetch(self) -> PizzaData:
        """Fetch and parse the current pizza index data."""
        logger.info(f"Fetching data from {self.url}")
        
        try:
            response = self.client.get(self.url)
            response.raise_for_status()
            html = response.text
            
            # Try to extract __NEXT_DATA__ first (Next.js SSR data)
            data = self._parse_next_data(html)
            if data:
                return data
            
            # Fallback to HTML parsing
            return self._parse_html(html)
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching pizza data: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching pizza data: {e}")
            raise
    
    def _parse_next_data(self, html: str) -> Optional[PizzaData]:
        """Extract data from Next.js __NEXT_DATA__ script tag."""
        soup = BeautifulSoup(html, "html.parser")
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        
        if not next_data_script:
            logger.debug("No __NEXT_DATA__ found, falling back to HTML parsing")
            return None
        
        try:
            next_data = json.loads(next_data_script.string)
            props = next_data.get("props", {}).get("pageProps", {})
            
            # Extract DOUGHCON level
            doughcon_level = self._extract_doughcon_from_props(props)
            if not doughcon_level:
                # Try finding it elsewhere in the data
                doughcon_level = self._find_doughcon_in_data(next_data)
            
            # Extract stores
            stores = self._extract_stores_from_props(props)
            
            if doughcon_level:
                return PizzaData(
                    doughcon_level=doughcon_level,
                    stores=stores,
                    raw_data=props
                )
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse __NEXT_DATA__: {e}")
        
        return None
    
    def _extract_doughcon_from_props(self, props: dict) -> Optional[int]:
        """Extract DOUGHCON level from page props."""
        # Common key patterns
        for key in ["doughcon", "defcon", "level", "threatLevel", "alertLevel"]:
            if key in props:
                value = props[key]
                if isinstance(value, int) and 1 <= value <= 5:
                    return value
                if isinstance(value, dict) and "level" in value:
                    return value["level"]
        return None
    
    def _find_doughcon_in_data(self, data: dict) -> Optional[int]:
        """Recursively search for DOUGHCON level in nested data."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in ["doughcon", "defcon", "level"]:
                    if isinstance(value, int) and 1 <= value <= 5:
                        return value
                result = self._find_doughcon_in_data(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_doughcon_in_data(item)
                if result:
                    return result
        return None
    
    def _extract_stores_from_props(self, props: dict) -> list[PizzaStore]:
        """Extract store data from page props."""
        stores = []
        
        # Look for stores/restaurants array
        for key in ["stores", "restaurants", "pizzaStores", "locations"]:
            if key in props and isinstance(props[key], list):
                for store_data in props[key]:
                    store = self._parse_store(store_data)
                    if store:
                        stores.append(store)
                break
        
        return stores
    
    def _parse_store(self, data: dict) -> Optional[PizzaStore]:
        """Parse a single store from data."""
        if not isinstance(data, dict):
            return None
        
        name = data.get("name") or data.get("title") or data.get("storeName")
        if not name:
            return None
        
        status = (data.get("status") or data.get("state") or "UNKNOWN").upper()
        activity = data.get("activity") or data.get("popularity") or data.get("busyPercent")
        distance = data.get("distance")
        
        return PizzaStore(
            name=name,
            status=status,
            activity_percent=float(activity) if activity else None,
            distance=str(distance) if distance else None
        )
    
    def _parse_html(self, html: str) -> PizzaData:
        """Fallback HTML parsing when __NEXT_DATA__ is not available."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Find DOUGHCON level from text
        doughcon_level = self._find_doughcon_in_html(soup)
        
        # Find stores from HTML structure
        stores = self._find_stores_in_html(soup)
        
        return PizzaData(
            doughcon_level=doughcon_level or 5,  # Default to 5 (lowest) if not found
            stores=stores
        )
    
    def _find_doughcon_in_html(self, soup: BeautifulSoup) -> Optional[int]:
        """Find DOUGHCON level by parsing HTML text."""
        # Look for text containing "DOUGHCON" followed by a number
        text = soup.get_text()
        
        patterns = [
            r"DOUGHCON\s*(\d)",
            r"DEFCON\s*(\d)",
            r"Level\s*(\d)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 5:
                    logger.info(f"Found DOUGHCON level {level} in HTML")
                    return level
        
        return None
    
    def _find_stores_in_html(self, soup: BeautifulSoup) -> list[PizzaStore]:
        """Find store cards in HTML structure."""
        stores = []
        
        # Look for common pizza chain names
        pizza_names = [
            "DOMINO'S", "PAPA JOHN'S", "PIZZA HUT", 
            "LITTLE CAESARS", "MARCO'S", "JETS"
        ]
        
        # Find elements containing pizza store names
        for name in pizza_names:
            elements = soup.find_all(string=re.compile(name, re.IGNORECASE))
            for el in elements:
                parent = el.find_parent()
                if parent:
                    # Try to find status nearby
                    status = "UNKNOWN"
                    card = parent
                    for _ in range(5):  # Go up to 5 levels
                        card = card.parent if card else None
                        if card:
                            card_text = card.get_text().upper()
                            if "CLOSED" in card_text:
                                status = "CLOSED"
                                break
                            elif "OPEN" in card_text:
                                status = "OPEN"
                                break
                            elif "BUSY" in card_text:
                                status = "BUSY"
                                break
                    
                    # Avoid duplicates
                    if not any(s.name.upper() == name.upper() for s in stores):
                        stores.append(PizzaStore(name=name, status=status))
        
        return stores
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
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
    print(f"Stores: {len(data.stores)}")
    for store in data.stores:
        print(f"  - {store.name}: {store.status}")
