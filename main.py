import os
import sys
import argparse
import logging
import time
import uvicorn
from urllib.parse import urlparse

# Import scraping and pipeline components
from src.scraper.manager import ScrapingManager
from src.scraper.engine import ScrapingEngine
from src.scraper.parser import ScrapingParser
from src.scraper.pipeline import DataPipeline

def setup_cli_logging():
    """Sets up neat command-line log output formatting."""
    log_format = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def run_cli_scraper(args):
    """Executes the scraper in synchronous terminal mode."""
    setup_cli_logging()
    logger = logging.getLogger("cli.main")
    
    logger.info("=" * 60)
    logger.info("APEX INDUSTRIAL SCRAPER - CLI MODE")
    logger.info("=" * 60)
    logger.info(f"Target URL: {args.url}")
    logger.info(f"Crawl Delay: {args.delay}s")
    logger.info(f"Respect Robots.txt: {not args.no_robots}")
    logger.info(f"Rotate User-Agents: {not args.no_rotate}")
    logger.info("-" * 60)
    
    # Instantiate engine, parser and pipeline
    engine = ScrapingEngine(
        request_delay=args.delay,
        respect_robots_txt=not args.no_robots,
        rotate_user_agents=not args.no_rotate
    )
    parser = ScrapingParser()
    pipeline = DataPipeline()
    
    current_url = args.url
    pages_count = 0
    items_count = 0
    start_time = time.time()
    
    try:
        while current_url:
            logger.info(f"Crawling index page: {current_url}")
            resp = engine.fetch(current_url)
            pages_count += 1
            
            # Extract links
            product_links = parser.extract_product_links(resp.text, current_url)
            logger.info(f"Discovered {len(product_links)} product detail links.")
            
            # Crawl each link
            for link in product_links:
                logger.info(f"Fetching product details: {link}")
                try:
                    p_resp = engine.fetch(link)
                    raw_item = parser.parse_product_detail(p_resp.text, link)
                    
                    # Simulating client dynamic AJAX retrieval if SKU matches local sandbox patterns
                    if "/sandbox/product/" in link:
                        sku = raw_item.get("sku")
                        if sku:
                            parsed_link = urlparse(link)
                            api_base = f"{parsed_link.scheme}://{parsed_link.netloc}"
                            api_url = f"{api_base}/sandbox/api/product/{sku}/details"
                            logger.info(f"Simulating API ajax fetch: {api_url}")
                            try:
                                api_resp = engine.fetch(api_url)
                                api_data = api_resp.json()
                                raw_item["stock_raw"] = str(api_data.get("stock", 0))
                                raw_item["rating_raw"] = str(api_data.get("rating", 0.0))
                            except Exception as api_err:
                                logger.warning(f"Could not retrieve dynamic details for {sku}: {api_err}")
                                
                    # Clean & validate
                    cleaned_item = pipeline.process_item(raw_item)
                    if cleaned_item:
                        items_count += 1
                        logger.info(f"-> Saved: {cleaned_item['sku']} | Price: ${cleaned_item['price']:.2f}")
                except Exception as p_err:
                    logger.error(f"Error scraping details from {link}: {p_err}")
            
            # Get next page link
            next_page = parser.extract_next_page(resp.text, current_url)
            if next_page:
                current_url = next_page
            else:
                current_url = None
                
    except Exception as e:
        logger.error(f"Critical error during crawl: {e}")
        
    duration = time.time() - start_time
    logger.info("=" * 60)
    logger.info("CRAWL COMPLETED")
    logger.info(f"Time Elapsed: {duration:.2f}s")
    logger.info(f"Total Pages Scraped: {pages_count}")
    logger.info(f"Total Items Extracted: {items_count}")
    logger.info("-" * 60)
    
    if items_count > 0:
        file_format = args.export.lower()
        if file_format == "excel" or file_format == "xlsx":
            output_file = args.output if args.output else "exports/scraped_products.xlsx"
            pipeline.export_to_excel(output_file)
            logger.info(f"Successfully saved Excel to: {os.path.abspath(output_file)}")
        else:
            output_file = args.output if args.output else "exports/scraped_products.csv"
            pipeline.export_to_csv(output_file)
            logger.info(f"Successfully saved CSV to: {os.path.abspath(output_file)}")
    else:
        logger.warning("No products scraped. Export skipped.")
        
    logger.info("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Apex Industrial Web Scraping & Data Extraction Console")
    
    # Server / Dashboard Arguments
    parser.add_argument("--host", default="127.0.0.1", help="Host address for Dashboard Web server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to run Dashboard Web server on (default: 8000)")
    
    # CLI mode arguments
    parser.add_argument("--cli", action="store_true", help="Launch scraper in Command Line Interface mode directly")
    parser.add_argument("--url", default="http://localhost:8000/sandbox", help="Starting URL to crawl in CLI mode")
    parser.add_argument("--delay", type=float, default=1.0, help="Wait delay between requests in seconds (default: 1.0)")
    parser.add_argument("--no-robots", action="store_true", help="Ignore robots.txt policies")
    parser.add_argument("--no-rotate", action="store_true", help="Disable User-Agent header rotation")
    parser.add_argument("--export", default="csv", choices=["csv", "excel", "xlsx"], help="Export format (default: csv)")
    parser.add_argument("--output", default="", help="Filepath to write the exported file (defaults under exports/)")
    
    args = parser.parse_args()
    
    if args.cli:
        run_cli_scraper(args)
    else:
        # Start server mode (Serving both Dashboard & Sandbox targets)
        print("=" * 60)
        print("APEX CRAWLOPS CONSOLE - LAUNCHING SERVER")
        print("=" * 60)
        print(f"URL Dashboard:   http://{args.host}:{args.port}/dashboard")
        print(f"URL Target:      http://{args.host}:{args.port}/sandbox")
        print("=" * 60)
        print("Press Ctrl+C to terminate the server.\n")
        
        # Starts Uvicorn runner
        uvicorn.run("src.sandbox.server:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
