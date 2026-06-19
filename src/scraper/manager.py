import time
import logging
import threading
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse

from src.scraper.engine import ScrapingEngine
from src.scraper.parser import ScrapingParser
from src.scraper.pipeline import DataPipeline

# Setup a custom logging handler to buffer logs for the Web Dashboard
class DashboardLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, record):
        log_entry = {
            "timestamp": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "message": self.format(record)
        }
        with self._lock:
            self.logs.append(log_entry)
            # Keep only the last 200 logs
            if len(self.logs) > 200:
                self.logs.pop(0)

    def get_logs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.logs)

    def clear(self):
        with self._lock:
            self.logs.clear()


# Create global logging handler instance
dashboard_log_handler = DashboardLogHandler()
# Set format to include level and message for dashboard console cleanliness
formatter = logging.Formatter('[%(levelname)s] %(message)s')
dashboard_log_handler.setFormatter(formatter)

# Configure package logging
root_logger = logging.getLogger("scraper")
root_logger.setLevel(logging.INFO)
root_logger.addHandler(dashboard_log_handler)

logger = logging.getLogger("scraper.manager")


class ScrapingManager:
    def __init__(self):
        self.engine: Optional[ScrapingEngine] = None
        self.parser = ScrapingParser()
        self.pipeline = DataPipeline()
        
        self.status = {
            "is_running": False,
            "is_paused": False,
            "pages_scraped": 0,
            "items_scraped": 0,
            "errors": 0,
            "current_target": "",
            "elapsed_time": 0.0,
            "status_text": "Idle"
        }
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set() # Unpaused by default
        self._start_time = 0.0

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and statistics of the scraper."""
        if self.status["is_running"] and not self.status["is_paused"]:
            self.status["elapsed_time"] = round(time.time() - self._start_time, 1)
        return self.status

    def start(self, start_url: str, delay: float = 1.0, respect_robots: bool = True, rotate_ua: bool = True):
        """Starts the scraping process in a background thread."""
        if self.status["is_running"]:
            logger.warning("Scraper is already running.")
            return

        self._stop_event.clear()
        self._pause_event.set()
        
        self.engine = ScrapingEngine(
            request_delay=delay,
            respect_robots_txt=respect_robots,
            rotate_user_agents=rotate_ua
        )
        
        # Reset counters
        self.pipeline.clear()
        self.status["is_running"] = True
        self.status["is_paused"] = False
        self.status["pages_scraped"] = 0
        self.status["items_scraped"] = 0
        self.status["errors"] = 0
        self.status["current_target"] = start_url
        self.status["status_text"] = "Initializing..."
        self._start_time = time.time()
        
        self._thread = threading.Thread(
            target=self._run_scraping_loop,
            args=(start_url,),
            daemon=True
        )
        self._thread.start()
        logger.info(f"Scraper started background thread targeting: {start_url}")

    def pause(self):
        """Pauses the execution loop."""
        if self.status["is_running"] and not self.status["is_paused"]:
            self._pause_event.clear()
            self.status["is_paused"] = True
            self.status["status_text"] = "Paused"
            logger.info("Scraping execution PAUSED by user.")

    def resume(self):
        """Resumes the execution loop."""
        if self.status["is_running"] and self.status["is_paused"]:
            self._pause_event.set()
            self.status["is_paused"] = False
            self.status["status_text"] = "Running"
            logger.info("Scraping execution RESUMED by user.")

    def stop(self):
        """Stops the scraper completely."""
        if self.status["is_running"]:
            self._stop_event.set()
            self._pause_event.set() # Unblock if paused
            self.status["status_text"] = "Stopping..."
            logger.info("Stopping scraper...")

    def _check_pause_and_stop(self) -> bool:
        """Helper to yield execution to pause or handle stops."""
        if self._stop_event.is_set():
            return True
            
        if not self._pause_event.is_set():
            self.status["status_text"] = "Paused"
            self._pause_event.wait()
            self.status["status_text"] = "Running"
            
        return self._stop_event.is_set()

    def _run_scraping_loop(self, start_url: str):
        """The main crawling loop executed in a background thread."""
        current_url = start_url
        self.status["status_text"] = "Running"
        
        try:
            while current_url:
                if self._check_pause_and_stop():
                    break

                logger.info(f"Crawling index page: {current_url}")
                self.status["current_target"] = current_url
                
                try:
                    # 1. Fetch index page
                    resp = self.engine.fetch(current_url)
                    self.status["pages_scraped"] += 1
                    
                    # 2. Extract product links
                    product_links = self.parser.extract_product_links(resp.text, current_url)
                    logger.info(f"Found {len(product_links)} products on index page.")
                    
                    # 3. Visit each product page
                    for link in product_links:
                        if self._check_pause_and_stop():
                            break
                            
                        logger.info(f"Detail crawl: {link}")
                        self.status["current_target"] = link
                        
                        try:
                            # Fetch detailed page
                            p_resp = self.engine.fetch(link)
                            raw_item = self.parser.parse_product_detail(p_resp.text, link)
                            
                            # Real-World Scenario: If rating or stock is missing in HTML,
                            # fetch it dynamically via AJAX from the Sandbox API
                            if not raw_item.get("stock_raw") or not raw_item.get("rating_raw"):
                                # If link is in sandbox, e.g. http://localhost:8000/sandbox/product/SKU-123
                                # we can query the API at http://localhost:8000/sandbox/api/product/SKU-123/details
                                sku = raw_item.get("sku")
                                if sku and "/sandbox/product/" in link:
                                    parsed_link = urlparse(link)
                                    api_base = f"{parsed_link.scheme}://{parsed_link.netloc}"
                                    api_url = f"{api_base}/sandbox/api/product/{sku}/details"
                                    
                                    logger.info(f"Simulating dynamic client-side AJAX fetch: {api_url}")
                                    try:
                                        api_resp = self.engine.fetch(api_url)
                                        api_data = api_resp.json()
                                        raw_item["stock_raw"] = str(api_data.get("stock", 0))
                                        raw_item["rating_raw"] = str(api_data.get("rating", 0.0))
                                        logger.info(f"Successfully retrieved dynamic stock ({raw_item['stock_raw']}) and rating ({raw_item['rating_raw']})")
                                    except Exception as api_err:
                                        logger.warning(f"Could not retrieve dynamic product details for {sku}: {api_err}")
                            
                            # Process and validate items through pipeline
                            cleaned = self.pipeline.process_item(raw_item)
                            if cleaned:
                                self.status["items_scraped"] += 1
                                
                        except Exception as e:
                            logger.error(f"Error scraping detail page {link}: {e}")
                            self.status["errors"] += 1
                            
                    # 4. Check for next page
                    if not self._check_pause_and_stop():
                        next_url = self.parser.extract_next_page(resp.text, current_url)
                        if next_url:
                            current_url = next_url
                            logger.info(f"Discovered pagination link: {next_url}")
                        else:
                            logger.info("No further pages found. Scraping completed.")
                            current_url = None
                            
                except Exception as e:
                    logger.error(f"Error crawling page {current_url}: {e}")
                    self.status["errors"] += 1
                    # If the starting page fails or is blocked, terminate the crawler
                    if current_url == start_url:
                        logger.error("Starting URL could not be crawled. Halting.")
                        break
                    # For middle page errors, we can try to proceed if we can, or halt
                    current_url = None
                    
        except Exception as main_err:
            logger.critical(f"Critical error in scraping manager loop: {main_err}")
            self.status["errors"] += 1
            
        finally:
            self.status["is_running"] = False
            self.status["is_paused"] = False
            self.status["status_text"] = "Completed" if not self._stop_event.is_set() else "Stopped"
            self.status["current_target"] = ""
            logger.info(f"Crawl finished. Scraped {self.status['pages_scraped']} pages, extracted {self.status['items_scraped']} items with {self.status['errors']} errors.")
