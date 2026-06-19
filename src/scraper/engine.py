import time
import random
import logging
import urllib.robotparser
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger("scraper.engine")

# A list of realistic, modern browser User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

class ScrapingEngine:
    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        respect_robots_txt: bool = True,
        rotate_user_agents: bool = True
    ):
        """
        Initializes the Scraping Engine with robust and ethical configurations.

        Args:
            request_delay: Minimum delay between requests in seconds.
            max_retries: Maximum number of retries for failed requests (e.g. 429, 5xx).
            backoff_factor: Factor for exponential backoff calculations.
            respect_robots_txt: Whether to fetch and respect robots.txt crawl rules.
            rotate_user_agents: Whether to rotate User-Agent headers for each request.
        """
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.respect_robots_txt = respect_robots_txt
        self.rotate_user_agents = rotate_user_agents
        
        self.session = requests.Session()
        self.robots_parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self.last_request_time: float = 0.0
        
        # Configure standard adapter with basic connection pools
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_robots_parser(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """Fetches and parses robots.txt for the given target domain if configured."""
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        if base_url in self.robots_parsers:
            return self.robots_parsers[base_url]
            
        robots_url = f"{base_url}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            logger.info(f"Checking robots.txt policy at: {robots_url}")
            # Use requests with a short timeout to fetch robots.txt to avoid freezing
            # robotparser's read() does synchronous blocking, so we can pre-fetch
            headers = {"User-Agent": USER_AGENTS[0]}
            resp = self.session.get(robots_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            elif resp.status_code == 404:
                # If robots.txt doesn't exist, assume allowed
                rp.parse([])
            else:
                # Other status codes: play it safe or assume allowed
                rp.parse([])
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt from {robots_url}: {e}. Proceeding with caution.")
            # Set an empty parse so it allows requests by default or fails safe
            rp.parse([])
            
        self.robots_parsers[base_url] = rp
        return rp

    def is_allowed(self, url: str, user_agent: str) -> bool:
        """Verifies if the specified URL path can be crawled based on robots.txt."""
        if not self.respect_robots_txt:
            return True
            
        rp = self._get_robots_parser(url)
        if not rp:
            return True
            
        allowed = rp.can_fetch(user_agent, url)
        if not allowed:
            logger.warning(f"URL access BLOCKED by robots.txt: {url}")
        return allowed

    def _get_headers(self) -> Dict[str, str]:
        """Generates request headers, rotating User-Agent if requested."""
        ua = random.choice(USER_AGENTS) if self.rotate_user_agents else USER_AGENTS[0]
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }

    def _apply_rate_limiting(self):
        """Applies a sleep delay with a randomized jitter between consecutive requests."""
        if self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            # Jitter is between 80% and 120% of the specified delay to simulate human actions
            jitter = random.uniform(0.8, 1.2)
            required_wait = self.request_delay * jitter
            if elapsed < required_wait:
                wait_time = required_wait - elapsed
                logger.debug(f"Rate limiting active. Waiting {wait_time:.2f}s...")
                time.sleep(wait_time)
        self.last_request_time = time.time()

    def fetch(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """
        Fetches the content of a URL with rotation headers, rate limiting, and robust retry logic.

        Args:
            url: The target URL to fetch.
            params: Optional query parameters.

        Returns:
            The HTTP response object.

        Raises:
            requests.exceptions.HTTPError: If the request fails after maximum retries.
        """
        headers = self._get_headers()
        ua = headers.get("User-Agent", "SystemScraper")
        
        # Check ethical compliance
        if not self.is_allowed(url, ua):
            raise PermissionError(f"Scraping this path is prohibited by robots.txt: {url}")

        attempt = 1
        current_delay = self.request_delay

        while attempt <= self.max_retries + 1:
            self._apply_rate_limiting()
            
            try:
                logger.info(f"Fetching URL: {url} (Attempt {attempt}/{self.max_retries + 1})")
                response = self.session.get(url, headers=headers, params=params, timeout=10)
                
                # Check for successful response
                if response.status_code == 200:
                    return response
                
                # If rate-limited (429) or server error (503, 504), wait and retry
                if response.status_code in [429, 500, 502, 503, 504]:
                    if attempt > self.max_retries:
                        logger.error(f"Max retries reached. Request failed with status {response.status_code}: {url}")
                        response.raise_for_status()
                    
                    # Exponential backoff with jitter
                    backoff = (self.backoff_factor ** attempt) * current_delay
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = backoff * jitter
                    
                    logger.warning(
                        f"HTTP {response.status_code} received. Retrying in {sleep_time:.2f}s... "
                        f"(Attempt {attempt}/{self.max_retries})"
                    )
                    time.sleep(sleep_time)
                    attempt += 1
                else:
                    # For other status codes (e.g. 403 Forbidden, 404 Not Found), don't retry and raise immediately
                    logger.error(f"Request failed immediately with status {response.status_code}: {url}")
                    response.raise_for_status()
                    
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt > self.max_retries:
                    logger.error(f"Max retries reached. Network error: {e}")
                    raise e
                    
                backoff = (self.backoff_factor ** attempt) * current_delay
                sleep_time = backoff * random.uniform(0.8, 1.2)
                logger.warning(f"Network error ({e}). Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                attempt += 1
                
        raise requests.exceptions.RequestException(f"Failed to fetch {url} after {self.max_retries} retries.")
