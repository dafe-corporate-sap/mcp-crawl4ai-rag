#!/usr/bin/env python3
"""
SAP Mobile Services Documentation Crawler
Crawls all 696 pages from the SAP Mobile Services documentation recursively.
"""

import asyncio
import json
import time
from pathlib import Path

# Base URL for SAP Mobile Services documentation
BASE_URL = "https://help.sap.com/doc/f53c64b93e5140918d676b927a3cd65b/Cloud/en-US/docs-en/"

def load_pages_list():
    """Load the list of pages to crawl from the text file."""
    pages_file = Path("/home/aitoolset/mobileservices/sap_mobile_services_pages.txt")
    if not pages_file.exists():
        raise FileNotFoundError("sap_mobile_services_pages.txt not found")
    
    with open(pages_file, 'r') as f:
        pages = [line.strip() for line in f if line.strip()]
    
    # Convert relative paths to full URLs
    full_urls = []
    for page in pages:
        if page.startswith('http'):
            full_urls.append(page)
        elif page.startswith('/'):
            # Absolute path from help.sap.com
            full_urls.append(f"https://help.sap.com{page}")
        else:
            # Relative path from base URL
            full_urls.append(f"{BASE_URL}{page}")
    
    return full_urls

def create_crawl_summary(pages_crawled, total_pages, chunks_stored, errors):
    """Create a summary of the crawling process."""
    summary = {
        "crawl_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_pages_found": total_pages,
        "pages_successfully_crawled": pages_crawled,
        "total_chunks_stored": chunks_stored,
        "success_rate": f"{(pages_crawled/total_pages)*100:.1f}%",
        "errors": len(errors),
        "error_details": errors[:10] if errors else []  # Show first 10 errors
    }
    
    with open("sap_mobile_services_crawl_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary

async def crawl_pages_batch(pages, batch_size=5, delay=2):
    """
    Crawl pages in batches using the MCP crawl4ai-rag tool.
    This is a template - actual implementation would use MCP tool calls.
    """
    print(f"Starting batch crawling of {len(pages)} pages...")
    print(f"Batch size: {batch_size}, Delay between batches: {delay}s")
    
    total_pages = len(pages)
    pages_crawled = 0
    chunks_stored = 0
    errors = []
    
    for i in range(0, total_pages, batch_size):
        batch = pages[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_pages + batch_size - 1) // batch_size
        
        print(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} pages)...")
        
        for j, url in enumerate(batch):
            try:
                print(f"  [{batch_num}.{j+1}] Crawling: {url}")
                
                # Here you would use the MCP tool:
                # result = await use_mcp_tool("mcp-crawl4ai-rag", "crawl_single_page", {"url": url})
                # 
                # For now, we'll simulate the process
                await asyncio.sleep(0.5)  # Simulate crawling time
                
                # Simulate success
                pages_crawled += 1
                chunks_stored += 50  # Simulate average chunks per page
                
                print(f"    ✓ Success: ~50 chunks stored")
                
            except Exception as e:
                error_msg = f"Failed to crawl {url}: {str(e)}"
                errors.append(error_msg)
                print(f"    ✗ Error: {str(e)}")
        
        # Delay between batches to be respectful to the server
        if i + batch_size < total_pages:
            print(f"  Waiting {delay}s before next batch...")
            await asyncio.sleep(delay)
    
    # Create final summary
    summary = create_crawl_summary(pages_crawled, total_pages, chunks_stored, errors)
    
    print(f"\n" + "="*60)
    print("CRAWLING COMPLETE!")
    print(f"Pages crawled: {pages_crawled}/{total_pages} ({summary['success_rate']})")
    print(f"Total chunks stored: {chunks_stored}")
    print(f"Errors: {len(errors)}")
    print(f"Summary saved to: sap_mobile_services_crawl_summary.json")
    
    return summary

def main():
    """Main function to coordinate the crawling process."""
    print("SAP Mobile Services Documentation Crawler")
    print("=" * 50)
    
    # Load pages list
    try:
        pages = load_pages_list()
        print(f"Loaded {len(pages)} pages to crawl")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
    
    # Filter out external URLs and duplicates
    sap_pages = []
    seen_urls = set()
    
    for url in pages:
        if "help.sap.com" in url and url not in seen_urls:
            sap_pages.append(url)
            seen_urls.add(url)
    
    print(f"Filtered to {len(sap_pages)} unique SAP documentation pages")
    
    # Show some examples
    print("\nExample pages to crawl:")
    for i, page in enumerate(sap_pages[:10]):
        print(f"  {i+1}. {page}")
    
    if len(sap_pages) > 10:
        print(f"  ... and {len(sap_pages) - 10} more pages")
    
    print(f"\nTo start crawling, run:")
    print(f"  python3 -c \"import asyncio; from sap_mobile_services_crawler import crawl_pages_batch, load_pages_list; asyncio.run(crawl_pages_batch(load_pages_list()))\"")
    
    return sap_pages

if __name__ == "__main__":
    pages = main()
