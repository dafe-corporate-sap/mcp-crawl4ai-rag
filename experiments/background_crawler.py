#!/usr/bin/env python3
"""
Background SAP Mobile Services Documentation Crawler
Automatically crawls all 685 pages using the MCP crawl4ai-rag server.
"""

import asyncio
import json
import time
import logging
import aiohttp
from pathlib import Path
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sap_crawler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# MCP Server configuration
MCP_SERVER_URL = "http://localhost:8051/sse"  # Adjust if your MCP server runs on different port
BASE_URL = "https://help.sap.com/doc/f53c64b93e5140918d676b927a3cd65b/Cloud/en-US/docs-en/"

class SAPDocumentationCrawler:
    def __init__(self, batch_size=5, delay_between_batches=3, delay_between_pages=1):
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.delay_between_pages = delay_between_pages
        self.session = None
        self.stats = {
            'total_pages': 0,
            'pages_crawled': 0,
            'pages_failed': 0,
            'total_chunks': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def load_pages_list(self) -> List[str]:
        """Load the list of pages to crawl from the text file."""
        pages_file = Path("/home/i039818/mobileservices/sap_mobile_services_pages.txt")
        if not pages_file.exists():
            raise FileNotFoundError("sap_mobile_services_pages.txt not found")
        
        with open(pages_file, 'r') as f:
            pages = [line.strip() for line in f if line.strip()]
        
        # Convert relative paths to full URLs
        full_urls = []
        seen_urls = set()
        
        for page in pages:
            if page.startswith('http'):
                url = page
            elif page.startswith('/'):
                url = f"https://help.sap.com{page}"
            else:
                url = f"{BASE_URL}{page}"
            
            # Filter to only SAP help pages and avoid duplicates
            if "help.sap.com" in url and url not in seen_urls:
                full_urls.append(url)
                seen_urls.add(url)
        
        return full_urls
    
    async def call_mcp_crawl_single_page(self, url: str) -> Dict[str, Any]:
        """Call the MCP crawl4ai tool directly using the same approach as Cline."""
        # Import the MCP crawl4ai module directly
        import sys
        import os
        
        # Add the MCP server source directory to Python path
        mcp_src_path = "/home/i039818/Cline/MCP/mcp-crawl4ai-rag/src"
        if mcp_src_path not in sys.path:
            sys.path.insert(0, mcp_src_path)
        
        try:
            # Import and use the crawl function directly
            from crawl4ai_mcp import crawl_single_page
            
            # Call the function directly
            result_json = await crawl_single_page(url)
            
            # Parse the JSON result
            import json
            result = json.loads(result_json)
            
            return result
            
        except ImportError as e:
            raise Exception(f"Failed to import MCP module: {str(e)}")
        except Exception as e:
            raise Exception(f"MCP call failed: {str(e)}")
    
    async def crawl_page(self, url: str) -> Dict[str, Any]:
        """Crawl a single page and return results."""
        try:
            logger.info(f"Crawling: {url}")
            result = await self.call_mcp_crawl_single_page(url)
            
            if result.get("success"):
                chunks_stored = result.get("chunks_stored", 0)
                self.stats['pages_crawled'] += 1
                self.stats['total_chunks'] += chunks_stored
                logger.info(f"✓ Success: {chunks_stored} chunks stored")
                return {"success": True, "chunks": chunks_stored, "url": url}
            else:
                error_msg = result.get("error", "Unknown error")
                self.stats['pages_failed'] += 1
                self.stats['errors'].append(f"{url}: {error_msg}")
                logger.error(f"✗ Failed: {error_msg}")
                return {"success": False, "error": error_msg, "url": url}
        
        except Exception as e:
            error_msg = str(e)
            self.stats['pages_failed'] += 1
            self.stats['errors'].append(f"{url}: {error_msg}")
            logger.error(f"✗ Exception: {error_msg}")
            return {"success": False, "error": error_msg, "url": url}
    
    async def crawl_batch(self, urls: List[str], batch_num: int, total_batches: int) -> List[Dict[str, Any]]:
        """Crawl a batch of URLs."""
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(urls)} pages)")
        
        results = []
        for i, url in enumerate(urls):
            result = await self.crawl_page(url)
            results.append(result)
            
            # Small delay between pages within a batch
            if i < len(urls) - 1:
                await asyncio.sleep(self.delay_between_pages)
        
        return results
    
    def save_progress(self, batch_num: int, total_batches: int):
        """Save current progress to a file."""
        progress = {
            "batch_completed": batch_num,
            "total_batches": total_batches,
            "stats": self.stats.copy(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open("crawl_progress.json", 'w') as f:
            json.dump(progress, f, indent=2)
    
    def create_final_summary(self):
        """Create final crawling summary."""
        self.stats['end_time'] = time.time()
        duration = self.stats['end_time'] - self.stats['start_time']
        
        summary = {
            "crawl_completed": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": duration,
            "duration_formatted": f"{duration//3600:.0f}h {(duration%3600)//60:.0f}m {duration%60:.0f}s",
            "total_pages": self.stats['total_pages'],
            "pages_successfully_crawled": self.stats['pages_crawled'],
            "pages_failed": self.stats['pages_failed'],
            "success_rate": f"{(self.stats['pages_crawled']/self.stats['total_pages'])*100:.1f}%",
            "total_chunks_stored": self.stats['total_chunks'],
            "average_chunks_per_page": f"{self.stats['total_chunks']/max(self.stats['pages_crawled'], 1):.1f}",
            "errors_count": len(self.stats['errors']),
            "first_10_errors": self.stats['errors'][:10]
        }
        
        with open("sap_mobile_services_crawl_final_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary
    
    async def crawl_all_pages(self):
        """Main method to crawl all pages."""
        logger.info("Starting SAP Mobile Services Documentation Crawler")
        logger.info("=" * 60)
        
        # Load pages
        try:
            pages = self.load_pages_list()
            self.stats['total_pages'] = len(pages)
            self.stats['start_time'] = time.time()
            logger.info(f"Loaded {len(pages)} pages to crawl")
        except Exception as e:
            logger.error(f"Failed to load pages: {e}")
            return
        
        # Calculate batches
        total_batches = (len(pages) + self.batch_size - 1) // self.batch_size
        logger.info(f"Processing in {total_batches} batches of {self.batch_size} pages each")
        logger.info(f"Delays: {self.delay_between_pages}s between pages, {self.delay_between_batches}s between batches")
        
        # Process batches
        for i in range(0, len(pages), self.batch_size):
            batch_urls = pages[i:i+self.batch_size]
            batch_num = (i // self.batch_size) + 1
            
            try:
                await self.crawl_batch(batch_urls, batch_num, total_batches)
                
                # Save progress after each batch
                self.save_progress(batch_num, total_batches)
                
                # Progress update
                logger.info(f"Batch {batch_num}/{total_batches} completed. "
                          f"Progress: {self.stats['pages_crawled']}/{self.stats['total_pages']} pages, "
                          f"{self.stats['total_chunks']} chunks stored")
                
                # Delay between batches (except for the last batch)
                if batch_num < total_batches:
                    logger.info(f"Waiting {self.delay_between_batches}s before next batch...")
                    await asyncio.sleep(self.delay_between_batches)
            
            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                continue
        
        # Create final summary
        summary = self.create_final_summary()
        
        logger.info("=" * 60)
        logger.info("CRAWLING COMPLETED!")
        logger.info(f"Duration: {summary['duration_formatted']}")
        logger.info(f"Pages crawled: {summary['pages_successfully_crawled']}/{summary['total_pages']} ({summary['success_rate']})")
        logger.info(f"Total chunks stored: {summary['total_chunks_stored']}")
        logger.info(f"Average chunks per page: {summary['average_chunks_per_page']}")
        logger.info(f"Errors: {summary['errors_count']}")
        logger.info(f"Final summary saved to: sap_mobile_services_crawl_final_summary.json")

async def main():
    """Main entry point."""
    async with SAPDocumentationCrawler(
        batch_size=3,  # Conservative batch size
        delay_between_batches=5,  # 5 seconds between batches
        delay_between_pages=2  # 2 seconds between pages
    ) as crawler:
        await crawler.crawl_all_pages()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Crawling interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
