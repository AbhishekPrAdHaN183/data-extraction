import re
import os
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

logger = logging.getLogger("scraper.pipeline")

class DataPipeline:
    def __init__(self):
        self.scraped_data: List[Dict[str, Any]] = []

    @staticmethod
    def clean_price(price_str: str) -> float:
        """
        Cleans currency string and converts it to float.
        Example: '$1,299.99' -> 1299.99
        """
        if not price_str:
            return 0.0
            
        # Remove currency symbols, commas, and trailing spaces
        cleaned = re.sub(r"[^\d\.]", "", price_str)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            logger.warning(f"Could not parse price float from: '{price_str}'")
            return 0.0

    @staticmethod
    def clean_stock(stock_str: str) -> int:
        """
        Extracts integer stock units from status string.
        Example: '45 items left in stock' -> 45
                 'Out of stock' -> 0
        """
        if not stock_str:
            return 0
            
        stock_str_lower = stock_str.lower()
        if "out of stock" in stock_str_lower or "unavailable" in stock_str_lower:
            return 0
            
        # Search for digits
        match = re.search(r"\d+", stock_str)
        if match:
            return int(match.group(0))
            
        if "in stock" in stock_str_lower or "available" in stock_str_lower:
            # If it says in stock but has no numbers, assume available (e.g. 1)
            return 1
            
        return 0

    @staticmethod
    def clean_rating(rating_str: str) -> float:
        """
        Cleans rating value.
        Example: '4.5 out of 5 stars' -> 4.5
                 '⭐⭐⭐' -> 3.0
        """
        if not rating_str:
            return 0.0
            
        # Count star emojis as fallback
        if "⭐" in rating_str:
            return float(rating_str.count("⭐"))
            
        # Search for pattern like '4.5' or '4.5/5'
        match = re.search(r"(\d+(\.\d+)?)", rating_str)
        if match:
            try:
                val = float(match.group(1))
                # Check for rating bounds (normalize out of 5)
                if val > 5.0 and "/10" in rating_str:
                    val = val / 2.0
                return min(val, 5.0)
            except ValueError:
                pass
                
        return 0.0

    @staticmethod
    def clean_text(text: str) -> str:
        """Removes duplicate whitespace, newlines, and strips padding."""
        if not text:
            return ""
        # Replace newlines/tabs with space
        cleaned = re.sub(r"\s+", " ", text)
        return cleaned.strip()

    def validate_item(self, item: Dict[str, Any]) -> bool:
        """
        Checks if item complies with schema specifications.
        Required: name, sku.
        SKU must match a basic alphanumeric format.
        """
        if not item.get("name"):
            logger.warning("Item failed validation: Missing name.")
            return False
            
        if not item.get("sku"):
            logger.warning(f"Item '{item.get('name')}' failed validation: Missing SKU.")
            return False
            
        # Check if SKU matches format (alphanumeric, dashes allowed)
        sku = str(item.get("sku"))
        if not re.match(r"^[a-zA-Z0-9\-]+$", sku):
            logger.warning(f"Item '{item.get('name')}' failed validation: Invalid SKU format '{sku}'.")
            return False
            
        return True

    def process_item(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Cleans, structures, and validates a raw scraped item.
        If valid, appends to the storage list and returns the cleaned item.
        """
        cleaned_item = {
            "name": self.clean_text(raw_item.get("name", "")),
            "sku": self.clean_text(raw_item.get("sku", "")),
            "category": self.clean_text(raw_item.get("category", "Uncategorized")),
            "price": self.clean_price(raw_item.get("price_raw", "")),
            "stock": self.clean_stock(raw_item.get("stock_raw", "")),
            "rating": self.clean_rating(raw_item.get("rating_raw", "")),
            "description": self.clean_text(raw_item.get("description", "")),
            "url": raw_item.get("url", "")
        }

        # Handle explicit API values if they are directly numbers/floats from AJAX requests
        if "price" in raw_item and isinstance(raw_item["price"], (int, float)):
            cleaned_item["price"] = float(raw_item["price"])
            
        if "stock" in raw_item and isinstance(raw_item["stock"], int):
            cleaned_item["stock"] = raw_item["stock"]
            
        if "rating" in raw_item and isinstance(raw_item["rating"], (int, float)):
            cleaned_item["rating"] = float(raw_item["rating"])

        if self.validate_item(cleaned_item):
            # Check for duplicates by SKU
            self.scraped_data = [d for d in self.scraped_data if d["sku"] != cleaned_item["sku"]]
            self.scraped_data.append(cleaned_item)
            logger.info(f"Successfully processed item: {cleaned_item['sku']} - {cleaned_item['name']}")
            return cleaned_item
            
        return None

    def get_dataframe(self) -> pd.DataFrame:
        """Returns the accumulated list of scraped items as a Pandas DataFrame."""
        return pd.DataFrame(self.scraped_data)

    def export_to_csv(self, filepath: str) -> str:
        """Exports scraped data to CSV format."""
        df = self.get_dataframe()
        # Create directories if they do not exist
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        df.to_csv(filepath, index=False, encoding="utf-8")
        logger.info(f"Data successfully exported to CSV: {filepath} ({len(df)} items)")
        return filepath

    def export_to_excel(self, filepath: str) -> str:
        """Exports scraped data to Excel format."""
        df = self.get_dataframe()
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        # Uses openpyxl engine
        df.to_excel(filepath, index=False, sheet_name="Scraped Products")
        logger.info(f"Data successfully exported to Excel: {filepath} ({len(df)} items)")
        return filepath

    def clear(self):
        """Clears all stored scraped data."""
        self.scraped_data.clear()
