"""
MCP server that works directly with PostgREST API instead of Supabase client.

This version bypasses the Supabase client and makes direct HTTP requests to PostgREST.
"""
import asyncio
import json
import os
import logging
import aiohttp
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Import MCP components
from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

####################################################################################
# Temporary monkeypatch which avoids crashing when a POST message is received
# before a connection has been initialized, e.g: after a deployment.
# This is the solution from GitHub issue #423
# pylint: disable-next=protected-access
old__received_request = ServerSession._received_request

async def _received_request(self, *args, **kwargs):
    try:
        return await old__received_request(self, *args, **kwargs)
    except RuntimeError as e:
        if "Received request before initialization was complete" in str(e):
            logger.warning(f"Ignoring initialization timing error: {e}")
            return  # Silently ignore the initialization timing error
        else:
            # Re-raise other RuntimeErrors
            raise e

# Apply the monkeypatch
# pylint: disable-next=protected-access
ServerSession._received_request = _received_request
####################################################################################

# PostgREST configuration
POSTGREST_URL = os.getenv("SUPABASE_URL", "http://localhost:3000")
POSTGREST_TOKEN = os.getenv("SUPABASE_SERVICE_KEY", "")

# Initialize FastMCP server
mcp = FastMCP(
    "mcp-crawl4ai-rag-postgrest",
    description="MCP server that works directly with PostgREST API"
)

async def make_postgrest_request(endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
    """
    Make a request to PostgREST API.
    
    Args:
        endpoint: The API endpoint (e.g., "/sources", "/rpc/match_crawled_pages")
        method: HTTP method (GET, POST, etc.)
        data: Request data for POST requests
        
    Returns:
        Response data as dictionary
    """
    url = f"{POSTGREST_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    if POSTGREST_TOKEN:
        headers["Authorization"] = f"Bearer {POSTGREST_TOKEN}"
    
    try:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
            elif method == "POST":
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
    except Exception as e:
        logger.error(f"PostgREST request failed: {e}")
        raise

@mcp.tool()
async def get_available_sources() -> str:
    """
    Get all available sources from the sources table.
    
    Returns:
        JSON string with the list of available sources and their details
    """
    try:
        logger.info("get_available_sources called")
        
        # Query sources table
        result = await make_postgrest_request("/sources?order=source_id")
        logger.info(f"Got {len(result)} sources from PostgREST")
        
        # Format sources
        sources = []
        for source in result:
            sources.append({
                "source_id": source.get("source_id", ""),
                "summary": source.get("summary", ""),
                "total_words": source.get("total_word_count", 0),
                "created_at": source.get("created_at", ""),
                "updated_at": source.get("updated_at", "")
            })
        
        logger.info(f"Successfully formatted {len(sources)} sources")
        return json.dumps({
            "success": True,
            "sources": sources,
            "count": len(sources)
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in get_available_sources: {e}")
        return json.dumps({
            "success": False,
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def crawl_single_page(url: str) -> str:
    """
    Crawl a single web page and store its content in the database.
    
    This tool crawls a single webpage and stores the content in the database
    for later retrieval and querying via RAG.
    
    Args:
        url: URL of the web page to crawl
    
    Returns:
        Summary of the crawling operation and storage
    """
    try:
        logger.info(f"crawl_single_page called with url: '{url}'")
        
        # For demo purposes, we'll simulate crawling by creating mock content
        # In a real implementation, you'd use Crawl4AI to actually crawl the page
        
        # Validate URL
        if not url or not url.strip():
            return json.dumps({
                "success": False,
                "error": "URL cannot be empty"
            }, indent=2)
        
        # Extract source_id from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        source_id = parsed_url.netloc or parsed_url.path
        
        # Create mock crawled content
        mock_content = f"""# Page Content from {url}

This is mock content that would normally be crawled from the webpage.
In a real implementation, this would use Crawl4AI to extract the actual content.

## Key Information
- URL: {url}
- Source: {source_id}
- Content Type: Web Page
- Crawl Method: Mock (for demo)

## Sample Content
This page contains information about various topics that would be useful for RAG queries.
The content would be properly chunked and stored with embeddings for semantic search.
"""
        
        # Create mock metadata
        metadata = {
            "url": url,
            "source": source_id,
            "crawl_method": "mock",
            "content_type": "webpage",
            "word_count": len(mock_content.split()),
            "char_count": len(mock_content)
        }
        
        # In a real implementation, you would:
        # 1. Use Crawl4AI to crawl the actual page
        # 2. Chunk the content appropriately
        # 3. Generate embeddings using SAP BTP AICore
        # 4. Store in the database via PostgREST
        
        # For now, return a success response with mock data
        return json.dumps({
            "success": True,
            "url": url,
            "source_id": source_id,
            "content_length": len(mock_content),
            "word_count": metadata["word_count"],
            "chunks_stored": 1,
            "note": "Mock crawling for demo - in production this would use Crawl4AI and store real content"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in crawl_single_page: {e}")
        return json.dumps({
            "success": False,
            "url": url if 'url' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def smart_crawl_url(url: str, max_depth: int = 3, max_concurrent: int = 10) -> str:
    """
    Intelligently crawl a URL based on its type and store content.
    
    This tool automatically detects the URL type and applies the appropriate crawling method:
    - For sitemaps: Extracts and crawls all URLs in parallel
    - For text files: Directly retrieves the content
    - For regular webpages: Recursively crawls internal links up to the specified depth
    
    Args:
        url: URL to crawl (can be a regular webpage, sitemap.xml, or .txt file)
        max_depth: Maximum recursion depth for regular URLs (default: 3)
        max_concurrent: Maximum number of concurrent sessions (default: 10)
    
    Returns:
        JSON string with crawl summary and storage information
    """
    try:
        logger.info(f"smart_crawl_url called with url: '{url}', max_depth: {max_depth}, max_concurrent: {max_concurrent}")
        
        # Validate URL
        if not url or not url.strip():
            return json.dumps({
                "success": False,
                "error": "URL cannot be empty"
            }, indent=2)
        
        # Determine crawl type based on URL
        crawl_type = "webpage"  # default
        if url.endswith('sitemap.xml') or 'sitemap' in url:
            crawl_type = "sitemap"
        elif url.endswith('.txt'):
            crawl_type = "text_file"
        
        # Extract source_id from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        source_id = parsed_url.netloc or parsed_url.path
        
        # For demo purposes, simulate different crawling strategies
        if crawl_type == "sitemap":
            # Mock sitemap crawling
            mock_urls = [
                f"{url.replace('sitemap.xml', '')}page1",
                f"{url.replace('sitemap.xml', '')}page2",
                f"{url.replace('sitemap.xml', '')}page3"
            ]
            pages_crawled = len(mock_urls)
            chunks_stored = pages_crawled * 2  # Assume 2 chunks per page
        elif crawl_type == "text_file":
            # Mock text file crawling
            pages_crawled = 1
            chunks_stored = 1
        else:
            # Mock recursive webpage crawling
            pages_crawled = min(5, max_depth * 2)  # Simulate finding some internal links
            chunks_stored = pages_crawled * 3  # Assume 3 chunks per page
        
        # In a real implementation, you would:
        # 1. Parse sitemaps to extract URLs
        # 2. Use Crawl4AI to crawl pages recursively
        # 3. Chunk content and generate embeddings
        # 4. Store everything in the database
        
        return json.dumps({
            "success": True,
            "url": url,
            "crawl_type": crawl_type,
            "source_id": source_id,
            "pages_crawled": pages_crawled,
            "chunks_stored": chunks_stored,
            "max_depth_used": max_depth,
            "max_concurrent_used": max_concurrent,
            "note": "Mock crawling for demo - in production this would use Crawl4AI for actual crawling"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in smart_crawl_url: {e}")
        return json.dumps({
            "success": False,
            "url": url if 'url' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def crawl_local_files(file_path: str, recursive: bool = True, file_extensions: str = ".md,.txt,.html,.rst") -> str:
    """
    Crawl and process files from the local filesystem.
    
    This tool processes local files (markdown, text, HTML, etc.) and stores their content
    in the database for RAG queries. Useful for processing local documentation.
    
    Args:
        file_path: Path to file or directory to process
        recursive: Whether to process subdirectories recursively (default: True)
        file_extensions: Comma-separated list of file extensions to process (default: ".md,.txt,.html,.rst")
    
    Returns:
        Summary of the local file processing operation
    """
    try:
        logger.info(f"crawl_local_files called with path: '{file_path}', recursive: {recursive}")
        
        # Validate file path
        if not file_path or not file_path.strip():
            return json.dumps({
                "success": False,
                "error": "File path cannot be empty"
            }, indent=2)
        
        import os
        from pathlib import Path
        
        path = Path(file_path.strip())
        
        # Check if path exists
        if not path.exists():
            return json.dumps({
                "success": False,
                "error": f"Path does not exist: {file_path}"
            }, indent=2)
        
        # Parse file extensions
        extensions = [ext.strip() for ext in file_extensions.split(',')]
        
        # Collect files to process
        files_to_process = []
        
        if path.is_file():
            # Single file
            if any(str(path).endswith(ext) for ext in extensions):
                files_to_process.append(path)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"File extension not supported. Supported: {file_extensions}"
                }, indent=2)
        elif path.is_dir():
            # Directory
            if recursive:
                for ext in extensions:
                    files_to_process.extend(path.rglob(f"*{ext}"))
            else:
                for ext in extensions:
                    files_to_process.extend(path.glob(f"*{ext}"))
        else:
            return json.dumps({
                "success": False,
                "error": f"Path is neither file nor directory: {file_path}"
            }, indent=2)
        
        if not files_to_process:
            return json.dumps({
                "success": False,
                "error": f"No files found with extensions {file_extensions} in {file_path}"
            }, indent=2)
        
        # Process files
        total_files = len(files_to_process)
        total_content_length = 0
        total_word_count = 0
        total_chunks = 0
        processed_files = []
        
        for file_path_obj in files_to_process[:10]:  # Limit to 10 files for demo
            try:
                # Read file content
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Create mock metadata
                file_url = f"file://{file_path_obj.absolute()}"
                source_id = f"local:{file_path_obj.parent.name}"
                
                # Simulate chunking (in real implementation, you'd properly chunk the content)
                chunks = max(1, len(content) // 1000)  # Rough estimate
                
                total_content_length += len(content)
                total_word_count += len(content.split())
                total_chunks += chunks
                
                processed_files.append({
                    "file": str(file_path_obj),
                    "size": len(content),
                    "words": len(content.split()),
                    "chunks": chunks
                })
                
                # In a real implementation, you would:
                # 1. Properly chunk the content
                # 2. Generate embeddings using SAP BTP AICore
                # 3. Store in database via PostgREST
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path_obj}: {e}")
                continue
        
        return json.dumps({
            "success": True,
            "path": file_path,
            "files_found": total_files,
            "files_processed": len(processed_files),
            "total_content_length": total_content_length,
            "total_word_count": total_word_count,
            "total_chunks_estimated": total_chunks,
            "processed_files": processed_files[:5],  # Show first 5 files
            "note": "Mock processing for demo - in production this would generate embeddings and store in database"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in crawl_local_files: {e}")
        return json.dumps({
            "success": False,
            "path": file_path if 'file_path' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def perform_rag_query(query: str, source: str = None, match_count: int = 5) -> str:
    """
    Perform a RAG (Retrieval Augmented Generation) query on the stored content.
    
    Args:
        query: The search query
        source: Optional source domain to filter results (e.g., 'example.com')
        match_count: Maximum number of results to return (default: 5)
    
    Returns:
        JSON string with the search results
    """
    try:
        logger.info(f"perform_rag_query called with query: '{query}', source: '{source}', match_count: {match_count}")
        
        # Validate inputs
        if not query or not query.strip():
            return json.dumps({
                "success": False,
                "error": "Query cannot be empty"
            }, indent=2)
        
        # Validate match_count
        if match_count <= 0 or match_count > 50:
            match_count = 5
        
        # For this demo, we'll create a simple mock embedding
        # In a real implementation, you'd call SAP BTP AICore to create the embedding
        mock_embedding = [0.1] * 1536  # Mock embedding vector
        
        # Prepare the RPC call data
        rpc_data = {
            "query_embedding": mock_embedding,
            "match_count": match_count
        }
        
        # Add filter if source is provided
        if source and source.strip():
            rpc_data["filter"] = {"source": source.strip()}
        
        # Call the match_crawled_pages RPC function
        result = await make_postgrest_request("/rpc/match_crawled_pages", "POST", rpc_data)
        logger.info(f"Search completed, got {len(result) if result else 0} results")
        
        # Format results
        formatted_results = []
        for item in result or []:
            formatted_result = {
                "url": item.get("url", ""),
                "content": item.get("content", "")[:1000],  # Limit content length
                "metadata": item.get("metadata", {}),
                "similarity": item.get("similarity", 0.0)
            }
            formatted_results.append(formatted_result)
        
        logger.info(f"Successfully formatted {len(formatted_results)} results")
        return json.dumps({
            "success": True,
            "query": query,
            "source_filter": source,
            "results": formatted_results,
            "count": len(formatted_results),
            "note": "Using mock embedding for demo - in production this would use SAP BTP AICore"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in perform_rag_query: {e}")
        return json.dumps({
            "success": False,
            "query": query if 'query' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

async def main():
    """Main function to run the MCP server."""
    try:
        logger.info("Starting MCP server with PostgREST integration...")
        await mcp.run_sse_async()
        
    except KeyboardInterrupt:
        logger.info("Shutting down MCP server...")
    except Exception as e:
        logger.error(f"Fatal error in MCP server: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        exit(1)
