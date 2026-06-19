import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

logger = logging.getLogger("scraper.parser")

class ScrapingParser:
    @staticmethod
    def parse_html(html_content: str) -> BeautifulSoup:
        """Helper to create a BeautifulSoup document from raw HTML."""
        return BeautifulSoup(html_content, "lxml")

    @staticmethod
    def is_honeypot(element: Tag) -> bool:
        """
        Detects if a given HTML element (typically a link) is a honeypot trap.
        Checks for inline CSS styles, CSS classes, attributes, or size properties that make the element invisible.
        """
        # 1. Check for standard HTML hidden attributes
        if element.has_attr("hidden") or element.get("aria-hidden") == "true":
            return True
            
        # 2. Check for typical honeypot css selectors/ids
        id_val = str(element.get("id", "")).lower()
        class_vals = [str(c).lower() for c in element.get("class", [])]
        
        honeypot_keywords = ["honeypot", "trap", "fake-link", "invisible-link"]
        if any(keyword in id_val for keyword in honeypot_keywords):
            return True
        if any(any(keyword in c for keyword in honeypot_keywords) for c in class_vals):
            return True

        # 3. Check for inline style that hides the element
        style = str(element.get("style", "")).lower()
        if style:
            # Check for display: none
            if "display" in style and re.search(r"display\s*:\s*none", style):
                return True
            # Check for visibility: hidden
            if "visibility" in style and re.search(r"visibility\s*:\s*hidden", style):
                return True
            # Check for opacity: 0
            if "opacity" in style and re.search(r"opacity\s*:\s*0", style):
                return True
            # Check for height: 0 or width: 0
            if re.search(r"width\s*:\s*0", style) or re.search(r"height\s*:\s*0", style):
                return True
            # Check for absolute positioning off-screen (e.g. left: -9999px)
            position_offscreen = re.search(r"left\s*:\s*-\d{3,}", style) or re.search(r"top\s*:\s*-\d{3,}", style)
            if position_offscreen:
                return True

        return False

    def extract_product_links(self, html_content: str, base_url: str) -> List[str]:
        """
        Extracts product detail URLs from a product list page.
        Filters out honeypot trap links and duplicates.
        """
        soup = self.parse_html(html_content)
        product_links = []
        
        # We look for anchor tags that point to details (e.g. contain /product/ or look like product details)
        # For the local sandbox, product details links look like /sandbox/product/<sku>
        anchors = soup.find_all("a", href=True)
        
        for anchor in anchors:
            # Skip honeypot links
            if self.is_honeypot(anchor):
                logger.warning(f"Bypassed honeypot link: {anchor.get('href')} with contents: {anchor.text.strip()}")
                continue
                
            href = anchor["href"]
            
            # Filter for links that appear to lead to product details
            if "/sandbox/product/" in href or "/product/" in href:
                full_url = urljoin(base_url, href)
                if full_url not in product_links:
                    product_links.append(full_url)
                    
        return product_links

    def extract_next_page(self, html_content: str, base_url: str) -> Optional[str]:
        """
        Looks for the "Next Page" pagination link and returns its full URL.
        """
        soup = self.parse_html(html_content)
        
        # Common pagination patterns (next, class contains next, rel="next")
        next_anchor = None
        
        # 1. Search for rel="next"
        next_anchor = soup.find("a", rel="next")
        
        # 2. Search for link text containing "next" or "Next" or "»"
        if not next_anchor:
            for a in soup.find_all("a", href=True):
                if self.is_honeypot(a):
                    continue
                text = a.get_text().strip().lower()
                if "next" in text or "»" in text or "page-next" in str(a.get("class", "")):
                    next_anchor = a
                    break
                    
        if next_anchor and next_anchor.has_attr("href"):
            return urljoin(base_url, next_anchor["href"])
            
        return None

    def parse_product_detail(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Parses elements of a product detail page.
        Returns a dictionary of raw, uncleaned attributes.
        """
        soup = self.parse_html(html_content)
        
        # Extract name: e.g. from <h1>
        name_tag = soup.find("h1")
        name = name_tag.get_text().strip() if name_tag else ""
        
        # Extract SKU: e.g., element with class "sku" or text matching SKU pattern
        sku_tag = soup.find(class_="sku") or soup.find(id="sku")
        sku = sku_tag.get_text().replace("SKU:", "").strip() if sku_tag else ""
        
        if not sku:
            # Try regex on whole page or specific sections to extract SKU
            sku_match = re.search(r"SKU\s*:\s*([A-Za-z0-9\-]+)", soup.get_text())
            if sku_match:
                sku = sku_match.group(1).strip()
                
        # Extract Category: e.g. breadcrumb or category element
        category_tag = soup.find(class_="category") or soup.find(class_="breadcrumb-item")
        category = category_tag.get_text().strip() if category_tag else "Uncategorized"
        
        # Extract Price: e.g. element with class "price" or text starting with $ or containing digits
        price_tag = soup.find(class_="price") or soup.find(id="price")
        price_text = price_tag.get_text().strip() if price_tag else ""
        
        # Extract Description: e.g. product-description class or generic text blocks
        desc_tag = soup.find(class_="description") or soup.find(id="description") or soup.find(class_="product-description")
        description = desc_tag.get_text().strip() if desc_tag else ""
        
        # Extracted elements return as strings; pipeline does final conversions and cleanups
        raw_data = {
            "name": name,
            "sku": sku,
            "category": category,
            "price_raw": price_text,
            "description": description,
            "url": url,
            # Placeholder for elements that are loaded dynamically (e.g. stock, rating)
            # The manager can fetch these from API details if HTML doesn't contain them
            "stock_raw": "",
            "rating_raw": ""
        }
        
        # Some detail pages might contain rating & stock directly (for static fallback test)
        stock_tag = soup.find(class_="stock") or soup.find(id="stock")
        if stock_tag:
            raw_data["stock_raw"] = stock_tag.get_text().strip()
            
        rating_tag = soup.find(class_="rating") or soup.find(id="rating")
        if rating_tag:
            raw_data["rating_raw"] = rating_tag.get_text().strip()
            
        return raw_data
