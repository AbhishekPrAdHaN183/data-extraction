import time
import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Response, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import logging

# Set up local server logger
logger = logging.getLogger("sandbox.server")

# Import scraper modules
from src.scraper.manager import ScrapingManager, dashboard_log_handler

app = FastAPI(title="Industrial Scraper Sandbox & Dashboard")

# Enable CORS for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Scraper Manager
scraper_manager = ScrapingManager()

# Sandbox State
sandbox_ban_db = {
    "is_banned": False,
    "banned_until": 0.0,
    "blocked_count": 0,
    "honeypot_triggers": 0
}
sandbox_request_timestamps: List[float] = []
sandbox_lock = threading.Lock()

# Mock Products database
MOCK_PRODUCTS = [
    # Sensors (Page 1)
    {
        "sku": "SKU-SENS-101",
        "name": "Apex Temperature Sensor Probe",
        "category": "Sensors",
        "price": "$45.50",
        "description": "High-accuracy industrial thermocouple probe for manufacturing tanks and heat chambers. Supports range -50C to +400C.",
        "stock": 120,
        "rating": 4.2
    },
    {
        "sku": "SKU-SENS-202",
        "name": "Apex Laser Rangefinder Lidar",
        "category": "Sensors",
        "price": "$320.00",
        "description": "Precision lidar distance sensor with millimeter accuracy, outdoor-rated IP67 housing, and standard RS-485 Modbus interface.",
        "stock": 15,
        "rating": 4.8
    },
    {
        "sku": "SKU-SENS-303",
        "name": "Apex Humidity Transmitter",
        "category": "Sensors",
        "price": "$89.90",
        "description": "Wall-mounted relative humidity and temperature transmitter with robust 4-20mA analog current loop output for HVAC telemetry.",
        "stock": 45,
        "rating": 3.9
    },
    # Pneumatics (Page 1 / Page 2)
    {
        "sku": "SKU-PNEU-404",
        "name": "Apex Dual-Acting Air Cylinder",
        "category": "Pneumatics",
        "price": "$115.00",
        "description": "Corrosion-resistant stainless steel pneumatic cylinder with 100mm stroke, dual-acting cushion, and magnetic sensor-ready piston.",
        "stock": 60,
        "rating": 4.5
    },
    {
        "sku": "SKU-PNEU-505",
        "name": "Apex 5/2 Way Solenoid Valve",
        "category": "Pneumatics",
        "price": "$62.25",
        "description": "Direct-acting single solenoid control valve. Operates on 24VDC with standard G1/4 threads and LED indicator plug.",
        "stock": 90,
        "rating": 4.1
    },
    {
        "sku": "SKU-PNEU-606",
        "name": "Apex Rotary Actuator",
        "category": "Pneumatics",
        "price": "$210.00",
        "description": "Compact rack and pinion pneumatic rotary actuator. 90-degree rotation with adjustable end-cushioning and clean anodized finish.",
        "stock": 8,
        "rating": 4.6
    },
    # Healthcare Diagnostics (Page 2 / Page 3)
    {
        "sku": "SKU-HLTH-707",
        "name": "Apex ECG Lead Cable",
        "category": "Healthcare Diagnostics",
        "price": "$24.99",
        "description": "Double-shielded 10-lead clinical electrocardiogram patient cable. Noise-resistant connectors compatible with major bedside monitors.",
        "stock": 250,
        "rating": 4.0
    },
    {
        "sku": "SKU-HLTH-808",
        "name": "Apex Pulse Oximeter Module",
        "category": "Healthcare Diagnostics",
        "price": "$135.00",
        "description": "OEM board for integrated pulse oximetry. Low power consumption with raw photoplethysmogram (PPG) and clinical oxygen level outputs.",
        "stock": 40,
        "rating": 4.4
    },
    {
        "sku": "SKU-HLTH-909",
        "name": "Apex NIBP Inflation Bulb",
        "category": "Healthcare Diagnostics",
        "price": "$18.50",
        "description": "Replacement manual blood pressure inflation bulb with air control trigger. Medical-grade latex-free rubber with ergonomic grip.",
        "stock": 180,
        "rating": 3.5
    },
    # Robotics (Page 3)
    {
        "sku": "SKU-ROBT-010",
        "name": "Apex 6-DOF Robotic Joint Servo",
        "category": "Robotics",
        "price": "$1,850.00",
        "description": "High-torque brushless DC actuator joint with built-in dual absolute encoders, harmonic gearing, and etherCAT industrial communication.",
        "stock": 3,
        "rating": 4.9
    },
    {
        "sku": "SKU-ROBT-011",
        "name": "Apex Vacuum Suction Gripper",
        "category": "Robotics",
        "price": "$295.00",
        "description": "Lightweight, smart air-suction gripper kit. Features digital pressure sensors for packaging, glass handling, and electronic assemblies.",
        "stock": 22,
        "rating": 4.3
    },
    {
        "sku": "SKU-ROBT-012",
        "name": "Apex Ultrasonic Transducer",
        "category": "Robotics",
        "price": "$12.80",
        "description": "Solid state sonar transducer module in threaded plastic housing. IP65 rated for water and dust resistance, ideal for factory AGVs.",
        "stock": 500,
        "rating": 3.8
    }
]

# ----------------- SANDBOX MIDDLEWARE & GATEKEEPERS -----------------

def check_sandbox_access(request: Request):
    """
    Simulates security rules: User-Agent checks, rate limiting, and honeypot banning.
    """
    ua = request.headers.get("user-agent", "").lower()
    path = request.url.path
    
    # 1. User-Agent gate
    if not ua or "python-requests" in ua:
        sandbox_ban_db["blocked_count"] += 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Standard scraping library detected. Custom User-Agent rotation required."
        )
        
    with sandbox_lock:
        # 2. Check if client is honeypot-banned
        now = time.time()
        if sandbox_ban_db["is_banned"]:
            if now < sandbox_ban_db["banned_until"]:
                sandbox_ban_db["blocked_count"] += 1
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access Denied: Temporary ban active due to Honeypot trap. Banned for another {int(sandbox_ban_db['banned_until'] - now)} seconds."
                )
            else:
                sandbox_ban_db["is_banned"] = False

        # 3. Rate limiting (maximum 5 requests per second)
        # Clear logs older than 1 second
        sandbox_request_timestamps.append(now)
        # Keep list under size 50
        if len(sandbox_request_timestamps) > 50:
            sandbox_request_timestamps.pop(0)
            
        recent_requests = [t for t in sandbox_request_timestamps if now - t < 1.0]
        if len(recent_requests) > 5:
            sandbox_ban_db["blocked_count"] += 1
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Maximum 5 requests per second allowed."
            )

# ----------------- MOCK ROBOTS.TXT & SANDBOX -----------------

@app.get("/robots.txt", response_class=Response)
def robots_txt():
    content = """User-agent: *
Crawl-delay: 1
Disallow: /sandbox/admin
Disallow: /admin
"""
    return Response(content=content, media_type="text/plain")

@app.get("/sandbox", response_class=HTMLResponse)
def sandbox_home(request: Request):
    check_sandbox_access(request)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Apex Industrial Supplies Portal</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; color: #333; }
            h1 { color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }
            .category-card { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            .product-link { font-weight: bold; color: #0066cc; text-decoration: none; }
            .product-link:hover { text-decoration: underline; }
            .footer { margin-top: 50px; font-size: 0.85em; color: #777; text-align: center; border-top: 1px solid #ddd; padding-top: 20px; }
        </style>
    </head>
    <body>
        <h1>Apex Industrial Parts Catalog</h1>
        <p>Welcome to the Apex parts portal. Browse our industry-grade inventory using the paginated catalog link below.</p>
        
        <div class="category-card">
            <h3>Catalog Inventory</h3>
            <p>We stock critical components for manufacturing, pneumatics, healthcare diagnostic gear, and collaborative robotics.</p>
            <p>👉 <a href="/sandbox/products?page=1" class="product-link">Browse Full Paginated Catalog</a></p>
        </div>
        
        <!-- Honeypot link - Invisible to humans, but bots usually parse and click it -->
        <a href="/sandbox/admin" style="display: none;" id="admin-trap">System Admin Login</a>
        
        <div class="footer">
            <p>&copy; 2026 Apex Industrial Supplies Inc. Crawl authorized with Crawl-Delay=1s.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/sandbox/products", response_class=HTMLResponse)
def sandbox_products(request: Request, page: int = 1):
    check_sandbox_access(request)
    
    items_per_page = 4
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    
    page_products = MOCK_PRODUCTS[start_idx:end_idx]
    
    # Check if there's a next page
    next_page = page + 1 if end_idx < len(MOCK_PRODUCTS) else None
    
    # HTML rendering
    product_rows = ""
    for p in page_products:
        product_rows += f"""
        <div style="background: white; padding: 15px; margin: 15px 0; border: 1px solid #eee; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <h4 style="margin: 0;"><a href="/sandbox/product/{p['sku']}" class="product-title" style="color: #0066cc; text-decoration: none;">{p['name']}</a></h4>
                <span class="price" style="font-weight: bold; color: #e44d26;">{p['price']}</span>
            </div>
            <p style="font-size: 0.9em; color: #666; margin: 10px 0;">Category: <span class="category">{p['category']}</span> | SKU: <span class="sku">{p['sku']}</span></p>
            <p style="margin: 0; font-size: 0.95em;">{p['description'][:100]}...</p>
        </div>
        """
        
    pagination_html = ""
    if next_page:
        pagination_html = f'<a href="/sandbox/products?page={next_page}" rel="next" style="display: inline-block; padding: 8px 16px; background-color: #0066cc; color: white; text-decoration: none; border-radius: 4px; font-weight: bold;">Next Page &raquo;</a>'
    else:
        pagination_html = '<span style="color: #999; font-style: italic;">End of Catalog</span>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Apex Catalog - Page {page}</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; color: #333; }}
            h1 {{ color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        </style>
    </head>
    <body>
        <p><a href="/sandbox" style="color: #777; text-decoration: none;">&laquo; Back to Portal</a></p>
        <h1>Apex Components Catalog (Page {page})</h1>
        
        <div class="product-list">
            {product_rows}
        </div>
        
        <div style="margin-top: 30px; text-align: right; padding-top: 15px; border-top: 1px solid #ddd;">
            {pagination_html}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/sandbox/product/{sku}", response_class=HTMLResponse)
def sandbox_product_detail(request: Request, sku: str):
    check_sandbox_access(request)
    
    product = next((p for p in MOCK_PRODUCTS if p["sku"] == sku), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Detail HTML page:
    # Crucially, rating and stock are NOT rendered statically in the HTML.
    # Instead, we serve dynamic placeholders (<span id="stock-val">Loading...</span>) and a javascript function that fetches
    # details from `/sandbox/api/product/{sku}/details`.
    # This demonstrates the requirement to scrape dynamic API content!
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{product['name']} - Apex Catalog</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; color: #333; }}
            h1 {{ color: #0066cc; margin-bottom: 5px; }}
            .details-box {{ background: white; padding: 25px; border-radius: 8px; border: 1px solid #ddd; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .metadata {{ color: #666; font-size: 0.9em; border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 15px; }}
            .dynamic-item {{ display: inline-block; padding: 5px 10px; background-color: #eef5fc; border-radius: 4px; font-weight: bold; margin-right: 15px; }}
            .price-tag {{ font-size: 1.5em; color: #e44d26; font-weight: bold; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <p><a href="javascript:history.back()" style="color: #777; text-decoration: none;">&laquo; Back to List</a></p>
        
        <div class="details-box">
            <h1>{product['name']}</h1>
            <div class="metadata">
                SKU: <span class="sku" id="sku">{product['sku']}</span> | 
                Category: <span class="category">{product['category']}</span>
            </div>
            
            <div class="price-tag" id="price">{product['price']}</div>
            
            <p style="line-height: 1.6; font-size: 1.05em;" class="description">{product['description']}</p>
            
            <!-- Dynamic elements loaded via API AJAX -->
            <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee;">
                <h4>Real-Time Inventory Status & Ratings (Dynamically Loaded)</h4>
                <div>
                    <span class="dynamic-item">Stock: <span id="stock-val" style="color:#0066cc;">Loading...</span></span>
                    <span class="dynamic-item">Rating: <span id="rating-val" style="color:#ff9900;">Loading...</span></span>
                </div>
            </div>
        </div>

        <script>
            // Simulate dynamic client-side JS requesting details from the JSON API
            fetch('/sandbox/api/product/{product['sku']}/details')
                .then(response => response.json())
                .then(data => {{
                    document.getElementById('stock-val').innerText = data.stock + ' units available';
                    document.getElementById('rating-val').innerText = data.rating + ' / 5.0';
                }})
                .catch(err => {{
                    document.getElementById('stock-val').innerText = 'Error loading stock';
                    document.getElementById('rating-val').innerText = 'Error loading rating';
                }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/sandbox/api/product/{sku}/details")
def sandbox_product_api_details(request: Request, sku: str):
    """
    API endpoint returning real-time details (stock, rating).
    Used by JavaScript in the product details page, and also by our advanced Scraper
    to bypass complex JS browser execution.
    """
    check_sandbox_access(request)
    
    product = next((p for p in MOCK_PRODUCTS if p["sku"] == sku), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product details not found")
        
    return {
        "sku": product["sku"],
        "stock": product["stock"],
        "rating": product["rating"]
    }

@app.get("/sandbox/admin", response_class=HTMLResponse)
def sandbox_honeypot_trap(request: Request):
    """
    Honeypot trap URL. If a bot accesses this, their session is banned from the sandbox!
    """
    with sandbox_lock:
        sandbox_ban_db["is_banned"] = True
        # Ban client for 60 seconds
        sandbox_ban_db["banned_until"] = time.time() + 60.0
        sandbox_ban_db["honeypot_triggers"] += 1
        
    logger.critical("Honeypot Triggered! Crawler detected accessing hidden /sandbox/admin link. Banned for 60 seconds.")
    
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Access Denied - Honeypot Trap</title></head>
    <body style="font-family:sans-serif; text-align:center; padding-top:100px; color:#c00;">
        <h1>TRAFFIC BLOCKED</h1>
        <p>This path (/sandbox/admin) is a honeypot trap. Your crawling agent has been blacklisted for 60 seconds.</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=403)


# ----------------- WEB SCRAPER DASHBOARD API ENDPOINTS -----------------

class StartScraperRequest(BaseModel):
    target_url: str
    delay: float = 1.0
    respect_robots: bool = True
    rotate_ua: bool = True

@app.post("/api/scraper/start")
def start_scraper(config: StartScraperRequest):
    if scraper_manager.status["is_running"]:
        return JSONResponse(status_code=400, content={"message": "Scraper is already running."})
        
    scraper_manager.start(
        start_url=config.target_url,
        delay=config.delay,
        respect_robots=config.respect_robots,
        rotate_ua=config.rotate_ua
    )
    return {"message": "Scraper started successfully."}

@app.post("/api/scraper/pause")
def pause_scraper():
    scraper_manager.pause()
    return {"message": "Scraper paused."}

@app.post("/api/scraper/resume")
def resume_scraper():
    scraper_manager.resume()
    return {"message": "Scraper resumed."}

@app.post("/api/scraper/stop")
def stop_scraper():
    scraper_manager.stop()
    return {"message": "Scraper stop signal sent."}

@app.get("/api/scraper/status")
def get_scraper_status():
    return scraper_manager.get_status()

@app.get("/api/scraper/logs")
def get_scraper_logs():
    return dashboard_log_handler.get_logs()

@app.post("/api/scraper/logs/clear")
def clear_scraper_logs():
    dashboard_log_handler.clear()
    return {"message": "Logs cleared."}

@app.get("/api/scraper/data")
def get_scraper_data():
    return scraper_manager.pipeline.scraped_data

@app.post("/api/sandbox/reset-ban")
def reset_sandbox_ban():
    with sandbox_lock:
        sandbox_ban_db["is_banned"] = False
        sandbox_ban_db["banned_until"] = 0.0
        sandbox_ban_db["blocked_count"] = 0
        sandbox_ban_db["honeypot_triggers"] = 0
    logger.info("Sandbox state manually reset. Crawler ban lifted.")
    return {"message": "Sandbox state reset successfully. Ban lifted."}

@app.get("/api/sandbox/status")
def get_sandbox_status():
    with sandbox_lock:
        now = time.time()
        active = sandbox_ban_db["is_banned"] and now < sandbox_ban_db["banned_until"]
        remaining = int(sandbox_ban_db["banned_until"] - now) if active else 0
        return {
            "is_banned": active,
            "seconds_remaining": remaining,
            "blocked_count": sandbox_ban_db["blocked_count"],
            "honeypot_triggers": sandbox_ban_db["honeypot_triggers"]
        }

@app.get("/api/scraper/export/{file_format}")
def export_scraped_data(file_format: str):
    """
    Generates and exports data in CSV or Excel, then serves it as a file response.
    """
    if len(scraper_manager.pipeline.scraped_data) == 0:
        raise HTTPException(status_code=400, detail="No scraped data available to export.")
        
    temp_dir = os.path.join(os.getcwd(), "exports")
    os.makedirs(temp_dir, exist_ok=True)
    
    if file_format.lower() == "csv":
        filepath = os.path.join(temp_dir, "scraped_products.csv")
        scraper_manager.pipeline.export_to_csv(filepath)
        return FileResponse(
            path=filepath, 
            filename="scraped_products.csv", 
            media_type="text/csv"
        )
    elif file_format.lower() == "xlsx" or file_format.lower() == "excel":
        filepath = os.path.join(temp_dir, "scraped_products.xlsx")
        scraper_manager.pipeline.export_to_excel(filepath)
        return FileResponse(
            path=filepath, 
            filename="scraped_products.xlsx", 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'excel'.")

# ----------------- SERVE DASHBOARD FRONTEND HTML -----------------

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard(request: Request):
    """
    Serves the beautiful interactive HTML Dashboard.
    """
    template_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    else:
        # Fallback raw UI if file doesn't exist yet
        return HTMLResponse(content="<h1>Dashboard HTML template not found. Ensure src/dashboard/templates/index.html is created.</h1>", status_code=404)
