#!/bin/bash
"""
SAP Mobile Services Documentation Crawler Runner
Runs the background crawler to ingest all 685 pages.
"""

echo "SAP Mobile Services Documentation Crawler"
echo "========================================"
echo ""

# Check if the pages list file exists
if [ ! -f "/home/i039818/mobileservices/sap_mobile_services_pages.txt" ]; then
    echo "Error: sap_mobile_services_pages.txt not found!"
    echo "Please run the page extraction first."
    exit 1
fi

# Count pages
PAGE_COUNT=$(wc -l < /home/i039818/mobileservices/sap_mobile_services_pages.txt)
echo "Found $PAGE_COUNT pages to crawl"
echo ""

# Check if MCP server is running (optional check)
echo "Starting background crawler..."
echo "This will crawl all pages using the MCP crawl4ai-rag server."
echo ""
echo "Progress will be logged to: sap_crawler.log"
echo "Progress will be saved to: crawl_progress.json"
echo "Final summary will be saved to: sap_mobile_services_crawl_final_summary.json"
echo ""

# Ask for confirmation
read -p "Do you want to start crawling all $PAGE_COUNT pages? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting crawler..."
    echo ""
    
    # Run the background crawler
    python3 background_crawler.py
    
    echo ""
    echo "Crawling completed! Check the log files for details."
else
    echo "Crawling cancelled."
fi
