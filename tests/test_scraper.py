import os
import pytest
import pandas as pd
from bs4 import BeautifulSoup

# Import code under test
from src.scraper.parser import ScrapingParser
from src.scraper.pipeline import DataPipeline

# ----------------- PARSER TESTS -----------------

def test_is_honeypot_detection():
    parser = ScrapingParser()
    
    # 1. Normal link
    normal_html = '<a href="/product/1">Normal Product</a>'
    normal_soup = BeautifulSoup(normal_html, "lxml")
    assert not parser.is_honeypot(normal_soup.find("a"))

    # 2. Hidden attribute link
    hidden_html = '<a href="/admin" hidden>Admin</a>'
    hidden_soup = BeautifulSoup(hidden_html, "lxml")
    assert parser.is_honeypot(hidden_soup.find("a"))

    # 3. display: none link
    disp_none_html = '<a href="/admin" style="display: none;">Admin</a>'
    disp_none_soup = BeautifulSoup(disp_none_html, "lxml")
    assert parser.is_honeypot(disp_none_soup.find("a"))

    # 4. visibility: hidden link
    vis_hidden_html = '<a href="/admin" style="padding: 10px; visibility: hidden; margin: 5px;">Admin</a>'
    vis_hidden_soup = BeautifulSoup(vis_hidden_html, "lxml")
    assert parser.is_honeypot(vis_hidden_soup.find("a"))

    # 5. honeypot in class/id
    class_trap_html = '<a href="/trap" class="btn fake-link-trap select">Fake</a>'
    class_trap_soup = BeautifulSoup(class_trap_html, "lxml")
    assert parser.is_honeypot(class_trap_soup.find("a"))

    # 6. opacity 0 link
    opacity_html = '<a href="/admin" style="opacity: 0;">Trap</a>'
    opacity_soup = BeautifulSoup(opacity_html, "lxml")
    assert parser.is_honeypot(opacity_soup.find("a"))


def test_extract_product_links():
    parser = ScrapingParser()
    base_url = "http://localhost:8000"
    
    html = """
    <div>
        <a href="/sandbox/product/SKU-1" id="link-1">Product 1</a>
        <a href="/sandbox/product/SKU-2" style="display: none;" id="trap">Product 2</a>
        <a href="/sandbox/product/SKU-3" class="honeypot">Product 3</a>
        <a href="/sandbox/product/SKU-4">Product 4</a>
        <a href="/other-page">Home</a>
    </div>
    """
    
    links = parser.extract_product_links(html, base_url)
    # Only SKU-1 and SKU-4 should be collected, SKU-2 and SKU-3 are honeypots
    assert len(links) == 2
    assert "http://localhost:8000/sandbox/product/SKU-1" in links
    assert "http://localhost:8000/sandbox/product/SKU-4" in links


def test_extract_next_page():
    parser = ScrapingParser()
    base_url = "http://localhost:8000/sandbox"
    
    # Test rel="next"
    html_rel = '<a href="/sandbox/products?page=2" rel="next">Next</a>'
    assert parser.extract_next_page(html_rel, base_url) == "http://localhost:8000/sandbox/products?page=2"
    
    # Test textual "Next"
    html_text = '<a href="/sandbox/products?page=3">Next Page &raquo;</a>'
    assert parser.extract_next_page(html_text, base_url) == "http://localhost:8000/sandbox/products?page=3"
    
    # Test none found
    html_none = '<a href="/sandbox/products?page=1">Page 1</a>'
    assert parser.extract_next_page(html_none, base_url) is None


def test_parse_product_detail():
    parser = ScrapingParser()
    url = "http://localhost:8000/sandbox/product/SKU-101"
    
    html = """
    <div class="product">
        <h1>Apex Temp Sensor</h1>
        <div class="sku">SKU: SKU-SENS-101</div>
        <div class="category">Sensors</div>
        <div class="price">$45.50</div>
        <div class="description">High accuracy probe.</div>
        <div class="stock">120 in stock</div>
        <div class="rating">4.2 stars</div>
    </div>
    """
    
    data = parser.parse_product_detail(html, url)
    assert data["name"] == "Apex Temp Sensor"
    assert data["sku"] == "SKU-SENS-101"
    assert data["category"] == "Sensors"
    assert data["price_raw"] == "$45.50"
    assert data["description"] == "High accuracy probe."
    assert data["stock_raw"] == "120 in stock"
    assert data["rating_raw"] == "4.2 stars"
    assert data["url"] == url


# ----------------- PIPELINE TESTS -----------------

def test_clean_price():
    assert DataPipeline.clean_price("$45.50") == 45.50
    assert DataPipeline.clean_price("$1,850.00") == 1850.00
    assert DataPipeline.clean_price("12.80") == 12.80
    assert DataPipeline.clean_price("") == 0.0
    assert DataPipeline.clean_price("Price: Call Us") == 0.0


def test_clean_stock():
    assert DataPipeline.clean_stock("120 units in stock") == 120
    assert DataPipeline.clean_stock("Out of stock") == 0
    assert DataPipeline.clean_stock("In stock") == 1
    assert DataPipeline.clean_stock("") == 0


def test_clean_rating():
    assert DataPipeline.clean_rating("4.2 out of 5 stars") == 4.2
    assert DataPipeline.clean_rating("⭐⭐⭐⭐") == 4.0
    assert DataPipeline.clean_rating("5.0 / 5.0") == 5.0
    assert DataPipeline.clean_rating("") == 0.0


def test_clean_text():
    assert DataPipeline.clean_text("  Apex   Sensor  \n Probe ") == "Apex Sensor Probe"
    assert DataPipeline.clean_text("") == ""


def test_validate_item():
    pipeline = DataPipeline()
    
    # Valid item
    valid_item = {"name": "Test Product", "sku": "SKU-TEST-123"}
    assert pipeline.validate_item(valid_item)

    # Invalid missing name
    invalid_no_name = {"name": "", "sku": "SKU-TEST-123"}
    assert not pipeline.validate_item(invalid_no_name)

    # Invalid missing sku
    invalid_no_sku = {"name": "Test Product", "sku": ""}
    assert not pipeline.validate_item(invalid_no_sku)

    # Invalid SKU characters
    invalid_sku_chars = {"name": "Test Product", "sku": "SKU_TEST_123$"}
    assert not pipeline.validate_item(invalid_sku_chars)


def test_pipeline_processing():
    pipeline = DataPipeline()
    
    raw_item = {
        "name": "  Apex Temp Sensor\n",
        "sku": "SKU-SENS-101",
        "category": "Sensors",
        "price_raw": "$45.50",
        "stock_raw": "120 in stock",
        "rating_raw": "4.2 stars",
        "description": "Probe thermometer.",
        "url": "http://localhost:8000/product/SKU-SENS-101"
    }
    
    processed = pipeline.process_item(raw_item)
    assert processed is not None
    assert processed["name"] == "Apex Temp Sensor"
    assert processed["price"] == 45.50
    assert processed["stock"] == 120
    assert processed["rating"] == 4.2
    assert processed["description"] == "Probe thermometer."
    
    # Ensure item was appended to scraped_data
    assert len(pipeline.scraped_data) == 1
    assert pipeline.scraped_data[0]["sku"] == "SKU-SENS-101"


def test_pipeline_export(tmp_path):
    pipeline = DataPipeline()
    item = {
        "name": "Apex Temp Sensor",
        "sku": "SKU-SENS-101",
        "category": "Sensors",
        "price_raw": "$45.50",
        "stock_raw": "120 in stock",
        "rating_raw": "4.2 stars",
        "description": "Probe thermometer.",
        "url": "http://localhost:8000/product/SKU-SENS-101"
    }
    pipeline.process_item(item)
    
    # Test CSV Export
    csv_file = tmp_path / "products.csv"
    pipeline.export_to_csv(str(csv_file))
    assert os.path.exists(csv_file)
    
    df_csv = pd.read_csv(csv_file)
    assert len(df_csv) == 1
    assert df_csv.loc[0, "sku"] == "SKU-SENS-101"
    assert df_csv.loc[0, "price"] == 45.50

    # Test Excel Export
    xlsx_file = tmp_path / "products.xlsx"
    pipeline.export_to_excel(str(xlsx_file))
    assert os.path.exists(xlsx_file)
    
    df_xlsx = pd.read_excel(xlsx_file)
    assert len(df_xlsx) == 1
    assert df_xlsx.loc[0, "sku"] == "SKU-SENS-101"
    assert df_xlsx.loc[0, "price"] == 45.50
