# SAP Mobile Services Documentation Crawler

This directory contains a comprehensive crawler system for recursively crawling and ingesting all 685+ pages from the SAP Mobile Services documentation at https://help.sap.com/doc/f53c64b93e5140918d676b927a3cd65b/Cloud/en-US/docs-en/

## 🎯 What This Does

- **Discovers** all HTML pages from the SAP Mobile Services documentation
- **Crawls** each page using Crawl4AI for high-quality content extraction
- **Chunks** content into optimal sizes for RAG (Retrieval Augmented Generation)
- **Generates embeddings** using SAP BTP AICore
- **Stores** everything in a PostgREST database for semantic search
- **Provides** comprehensive logging and progress tracking

## 📁 Files Overview

### Core Components

1. **`src/crawl4ai_mcp.py`** - Fixed MCP server with proper storage implementation
2. **`background_crawler.py`** - Main background crawler that processes all pages
3. **`sap_mobile_services_crawler.py`** - Helper script for page discovery and organization
4. **`run_sap_crawler.sh`** - Easy-to-use shell script to start crawling

### Data Files

- **`/home/i039818/mobileservices/sap_mobile_services_pages.txt`** - List of 696 discovered pages
- **`sap_crawler.log`** - Detailed crawling logs
- **`crawl_progress.json`** - Real-time progress tracking
- **`sap_mobile_services_crawl_final_summary.json`** - Final crawling summary

## 🚀 Quick Start

### Prerequisites

1. **MCP Server Running**: Ensure the mcp-crawl4ai-rag server is running
2. **SAP BTP AICore**: Configured with proper environment variables
3. **PostgREST Database**: Available and configured
4. **Pages List**: The `sap_mobile_services_pages.txt` file exists

### Option 1: Use the Shell Script (Recommended)

```bash
cd /home/i039818/Cline/MCP/mcp-crawl4ai-rag
./run_sap_crawler.sh
```

### Option 2: Run Python Directly

```bash
cd /home/i039818/Cline/MCP/mcp-crawl4ai-rag
python3 background_crawler.py
```

### Option 3: Custom Configuration

```python
from background_crawler import SAPDocumentationCrawler
import asyncio

async def custom_crawl():
    async with SAPDocumentationCrawler(
        batch_size=5,           # Pages per batch
        delay_between_batches=3, # Seconds between batches
        delay_between_pages=1    # Seconds between pages
    ) as crawler:
        await crawler.crawl_all_pages()

asyncio.run(custom_crawl())
```

## 📊 What Gets Crawled

The crawler processes **685 unique pages** including:

### Documentation Sections
- **Getting Started** - Setup guides for Android, iOS, MDK
- **Features** - Push notifications, security, offline data, etc.
- **Guides** - Step-by-step tutorials and best practices
- **API Reference** - Complete API documentation
- **Troubleshooting** - Common issues and solutions
- **Release Notes** - What's new and migration guides
- **Sample Code** - Code examples and templates

### Content Types
- Technical documentation
- Code samples and snippets
- Configuration guides
- Architecture diagrams (as text descriptions)
- API specifications
- Troubleshooting guides

## 🔧 Configuration

### Crawler Settings

The background crawler can be configured with these parameters:

```python
SAPDocumentationCrawler(
    batch_size=3,              # Conservative: 3 pages per batch
    delay_between_batches=5,   # 5 seconds between batches
    delay_between_pages=2      # 2 seconds between individual pages
)
```

### MCP Server Settings

Ensure your MCP server is configured with:
- **SAP BTP AICore** credentials for embeddings
- **PostgREST** database connection
- **Crawl4AI** for content extraction

## 📈 Progress Monitoring

### Real-time Monitoring

```bash
# Watch the log file
tail -f sap_crawler.log

# Check current progress
cat crawl_progress.json | jq '.'
```

### Progress File Format

```json
{
  "batch_completed": 45,
  "total_batches": 228,
  "stats": {
    "total_pages": 685,
    "pages_crawled": 135,
    "pages_failed": 0,
    "total_chunks": 6750
  },
  "timestamp": "2025-09-09 13:15:30"
}
```

## 📋 Expected Results

### Crawling Statistics
- **Total Pages**: ~685 unique documentation pages
- **Estimated Duration**: 2-4 hours (depending on configuration)
- **Expected Chunks**: ~30,000-50,000 content chunks
- **Storage Size**: Several GB of embedded content

### Success Metrics
- **Success Rate**: Target >95% successful crawls
- **Average Chunks/Page**: ~50-100 chunks per page
- **Content Quality**: High-quality markdown extraction via Crawl4AI

## 🔍 Post-Crawling Usage

Once crawling is complete, you can query the documentation:

```python
# Using the MCP tool
result = await use_mcp_tool("mcp-crawl4ai-rag", "perform_rag_query", {
    "query": "How to implement push notifications in Android",
    "source": "help.sap.com",
    "match_count": 5
})
```

### Example Queries
- "SAP Mobile Services authentication setup"
- "Offline OData synchronization Android"
- "Push notifications configuration iOS"
- "MDK custom controls development"
- "Mobile security best practices"

## 🛠️ Troubleshooting

### Common Issues

1. **MCP Server Not Running**
   ```bash
   # Check if MCP server is running
   curl -X POST http://localhost:3001/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'
   ```

2. **Missing Environment Variables**
   - Check SAP BTP AICore credentials
   - Verify PostgREST connection settings

3. **Rate Limiting**
   - Increase delays between requests
   - Reduce batch size

4. **Memory Issues**
   - Monitor system resources
   - Reduce concurrent processing

### Recovery from Interruption

The crawler saves progress after each batch. To resume:

1. Check `crawl_progress.json` for last completed batch
2. Modify the crawler to start from that batch
3. Re-run the crawler

## 📊 Final Summary

After completion, check `sap_mobile_services_crawl_final_summary.json`:

```json
{
  "crawl_completed": "2025-09-09 15:30:45",
  "duration_formatted": "2h 15m 30s",
  "total_pages": 685,
  "pages_successfully_crawled": 680,
  "success_rate": "99.3%",
  "total_chunks_stored": 45230,
  "average_chunks_per_page": "66.5"
}
```

## 🎉 Success!

Once crawling is complete, you'll have:
- ✅ Complete SAP Mobile Services documentation indexed
- ✅ Semantic search capabilities via embeddings
- ✅ RAG-ready content for AI-powered queries
- ✅ Comprehensive documentation knowledge base

The crawled content will be available through the MCP server's RAG query functionality, enabling powerful semantic search across the entire SAP Mobile Services documentation.
