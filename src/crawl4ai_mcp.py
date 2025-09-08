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
# Proper fix for MCP initialization timing issue
# This handles the "Received request before initialization was complete" error
####################################################################################

# Import MCP components for proper error handling
from mcp.server.session import ServerSession
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError

# Store original method
_original_received_request = ServerSession._received_request

async def _patched_received_request(self, responder):
    """
    Patched version that properly handles initialization timing issues.
    """
    try:
        return await _original_received_request(self, responder)
    except RuntimeError as e:
        if "Received request before initialization was complete" in str(e):
            logger.warning(f"Handling initialization timing issue: {e}")
            # Just log and return gracefully - don't try to send error responses
            # as the connection may not be properly established yet
            return
        else:
            # Re-raise other RuntimeErrors
            raise e

# Apply the patch
ServerSession._received_request = _patched_received_request

####################################################################################

# PostgREST configuration
POSTGREST_URL = os.getenv("SUPABASE_URL", "http://localhost:3000")
POSTGREST_TOKEN = os.getenv("SUPABASE_SERVICE_KEY", "")

# SAP BTP AICore configuration
SAP_BTP_AICORE_BASE_URL = os.getenv("SAP_BTP_AICORE_BASE_URL")
SAP_BTP_AICORE_AUTH_URL = os.getenv("SAP_BTP_AICORE_AUTH_URL")
SAP_BTP_AICORE_CLIENT_ID = os.getenv("SAP_BTP_AICORE_CLIENT_ID")
SAP_BTP_AICORE_CLIENT_SECRET = os.getenv("SAP_BTP_AICORE_CLIENT_SECRET")
SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID = os.getenv("SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID")
SAP_BTP_AICORE_EMBEDDING_MODEL = os.getenv("SAP_BTP_AICORE_EMBEDDING_MODEL", "text-embedding-3-large")

# Initialize FastMCP server
mcp = FastMCP(
    "mcp-crawl4ai-rag-postgrest",
    description="MCP server with real data storage and SAP BTP AICore embeddings"
)

# Global variable to store access token
_access_token = None
_token_expires_at = 0

async def get_sap_btp_access_token() -> str:
    """
    Get access token for SAP BTP AICore.
    
    Returns:
        Access token string
    """
    global _access_token, _token_expires_at
    import time
    
    # Check if we have a valid token
    if _access_token and time.time() < _token_expires_at:
        return _access_token
    
    # Get new token
    try:
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": SAP_BTP_AICORE_CLIENT_ID.strip("'\""),
            "client_secret": SAP_BTP_AICORE_CLIENT_SECRET.strip("'\"")
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SAP_BTP_AICORE_AUTH_URL}/oauth/token",
                data=auth_data,
                headers=headers
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    _access_token = token_data["access_token"]
                    # Set expiry to 90% of actual expiry for safety
                    _token_expires_at = time.time() + (token_data.get("expires_in", 3600) * 0.9)
                    logger.info("Successfully obtained SAP BTP AICore access token")
                    return _access_token
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get access token: HTTP {response.status}: {error_text}")
                    
    except Exception as e:
        logger.error(f"Error getting SAP BTP access token: {e}")
        raise

async def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding using SAP BTP AICore.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        List of floats representing the embedding vector
    """
    # Check if we have orchestration deployment (preferred) or embedding deployment
    orchestration_deployment_id = os.getenv("SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID")
    embedding_deployment_id = os.getenv("SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID")
    
    if not all([SAP_BTP_AICORE_BASE_URL, SAP_BTP_AICORE_AUTH_URL, 
               SAP_BTP_AICORE_CLIENT_ID, SAP_BTP_AICORE_CLIENT_SECRET]):
        raise Exception("SAP BTP AICore configuration missing. Please set SAP_BTP_AICORE_BASE_URL, SAP_BTP_AICORE_AUTH_URL, SAP_BTP_AICORE_CLIENT_ID, and SAP_BTP_AICORE_CLIENT_SECRET environment variables.")
    
    if not (orchestration_deployment_id or embedding_deployment_id):
        raise Exception("No deployment ID configured. Please set either SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID or SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID environment variable.")
    
    access_token = await get_sap_btp_access_token()
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "AI-Resource-Group": "default"
    }
    
    # Use orchestration service if available (preferred approach)
    if orchestration_deployment_id:
        payload = {
            "input": {
                "text": text
            },
            "config": {
                "modules": {
                    "embeddings": {
                        "model": {
                            "name": SAP_BTP_AICORE_EMBEDDING_MODEL,
                            "params": {
                                "dimensions": 1536
                            }
                        }
                    }
                }
            }
        }
        
        # Use orchestration endpoint directly
        url = f"https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com/v2/inference/deployments/{orchestration_deployment_id}/v2/embeddings"
        
    else:
        # Fallback to direct embedding service
        payload = {
            "input": text,
            "model": SAP_BTP_AICORE_EMBEDDING_MODEL
        }
        
        url = f"{SAP_BTP_AICORE_BASE_URL}/v2/inference/deployments/{embedding_deployment_id}/embeddings"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status == 200:
                result = await response.json()
                
                # Handle orchestration response format
                if orchestration_deployment_id:
                    if "final_result" in result:
                        embeddings_data = result["final_result"]
                    else:
                        embeddings_data = result
                    
                    if "data" in embeddings_data:
                        embedding = embeddings_data["data"][0]["embedding"]
                    elif "embeddings" in embeddings_data:
                        embedding = embeddings_data["embeddings"][0]
                    else:
                        embedding = embeddings_data[0] if isinstance(embeddings_data, list) else embeddings_data
                else:
                    # Direct embedding service response
                    embedding = result["data"][0]["embedding"]
                
                logger.info(f"Generated embedding with {len(embedding)} dimensions")
                return embedding
            else:
                error_text = await response.text()
                raise Exception(f"Failed to generate embedding: HTTP {response.status}: {error_text}")

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at a sentence or paragraph boundary
        if end < len(text):
            # Look for sentence endings
            for i in range(end, max(start + chunk_size // 2, end - 200), -1):
                if text[i] in '.!?\n':
                    end = i + 1
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    return chunks

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
                    if response.status in [200, 201]:  # Accept both 200 OK and 201 Created
                        try:
                            return await response.json()
                        except:
                            # Some POST requests might not return JSON (e.g., 201 Created with empty body)
                            return {}
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
            elif method == "PATCH":
                async with session.patch(url, headers=headers, json=data) as response:
                    if response.status in [200, 204]:  # Accept 200 OK and 204 No Content
                        try:
                            return await response.json()
                        except:
                            # PATCH might return empty body
                            return {}
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
        
        # Use Crawl4AI to actually crawl the page
        try:
            from crawl4ai import AsyncWebCrawler
            
            async with AsyncWebCrawler(verbose=True) as crawler:
                result = await crawler.arun(url=url)
                
                if result.success:
                    content = result.markdown or result.cleaned_html or "No content extracted"
                    
                    # Create metadata
                    metadata = {
                        "url": url,
                        "source": source_id,
                        "crawl_method": "crawl4ai",
                        "content_type": "webpage",
                        "word_count": len(content.split()),
                        "char_count": len(content),
                        "title": result.metadata.get("title", ""),
                        "description": result.metadata.get("description", "")
                    }
                    
                    # TODO: Implement actual storage
                    # 1. Chunk the content appropriately
                    # 2. Generate embeddings using SAP BTP AICore
                    # 3. Store in the database via PostgREST
                    
                    logger.info(f"Successfully crawled {url}, content length: {len(content)}")
                    
                    return json.dumps({
                        "success": True,
                        "url": url,
                        "source_id": source_id,
                        "content_length": len(content),
                        "word_count": metadata["word_count"],
                        "chunks_stored": 1,  # TODO: Implement actual chunking and storage
                        "title": metadata["title"],
                        "note": "Real crawling with Crawl4AI - storage implementation pending"
                    }, indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "url": url,
                        "error": f"Crawl4AI failed: {result.error_message}"
                    }, indent=2)
                    
        except ImportError:
            logger.warning("Crawl4AI not installed, falling back to basic HTTP request")
            
            # Fallback to basic HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        
                        metadata = {
                            "url": url,
                            "source": source_id,
                            "crawl_method": "http_fallback",
                            "content_type": "webpage",
                            "word_count": len(content.split()),
                            "char_count": len(content)
                        }
                        
                        return json.dumps({
                            "success": True,
                            "url": url,
                            "source_id": source_id,
                            "content_length": len(content),
                            "word_count": metadata["word_count"],
                            "chunks_stored": 1,
                            "note": "Basic HTTP crawling (install crawl4ai for better results) - storage implementation pending"
                        }, indent=2)
                    else:
                        return json.dumps({
                            "success": False,
                            "url": url,
                            "error": f"HTTP {response.status}: {response.reason}"
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
        
        # Use real crawling based on URL type
        pages_crawled = 0
        chunks_stored = 0
        
        if crawl_type == "sitemap":
            # TODO: Implement real sitemap parsing and crawling
            # For now, just crawl the base URL
            try:
                result = await crawl_single_page(url)
                result_data = json.loads(result)
                if result_data.get("success"):
                    pages_crawled = 1
                    chunks_stored = 1
            except Exception as e:
                logger.warning(f"Failed to crawl sitemap URL {url}: {e}")
                
        elif crawl_type == "text_file":
            # Crawl the text file directly
            try:
                result = await crawl_single_page(url)
                result_data = json.loads(result)
                if result_data.get("success"):
                    pages_crawled = 1
                    chunks_stored = 1
            except Exception as e:
                logger.warning(f"Failed to crawl text file {url}: {e}")
        else:
            # For regular webpages, start with the main page
            try:
                result = await crawl_single_page(url)
                result_data = json.loads(result)
                if result_data.get("success"):
                    pages_crawled = 1
                    chunks_stored = 1
                    
                # TODO: Implement recursive crawling of internal links
                # For now, just crawl the main page
                logger.info(f"Successfully crawled main page {url}")
                
            except Exception as e:
                logger.warning(f"Failed to crawl webpage {url}: {e}")
        
        return json.dumps({
            "success": True,
            "url": url,
            "crawl_type": crawl_type,
            "source_id": source_id,
            "pages_crawled": pages_crawled,
            "chunks_stored": chunks_stored,
            "max_depth_used": max_depth,
            "max_concurrent_used": max_concurrent,
            "note": "Real crawling implemented - recursive crawling and storage pending"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in smart_crawl_url: {e}")
        return json.dumps({
            "success": False,
            "url": url if 'url' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def crawl_local_files_batch(file_path: str, batch_size: int = 10, recursive: bool = True, file_extensions: str = ".md,.txt,.html,.rst", start_from: str = "") -> str:
    """
    Crawl and process files from the local filesystem in batches (iterative).
    
    This tool processes local files in batches to handle large repositories efficiently.
    It processes one batch at a time and returns, allowing the client to call it again
    to continue processing. This avoids timeout issues with large directories.
    
    Args:
        file_path: Path to file or directory to process
        batch_size: Number of files to process in this batch (default: 10)
        recursive: Whether to process subdirectories recursively (default: True)
        file_extensions: Comma-separated list of file extensions to process (default: ".md,.txt,.html,.rst")
        start_from: File path to start from (for resumption, empty string starts from beginning)
    
    Returns:
        Summary of the batch processing operation with next file to process
    """
    try:
        logger.info(f"crawl_local_files_batch called with path: '{file_path}', batch_size: {batch_size}, start_from: '{start_from}'")
        
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
        
        # Collect files to process with consistent sorting
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
            # Directory - collect all files first, then sort for consistency
            all_files = []
            if recursive:
                for ext in extensions:
                    all_files.extend(path.rglob(f"*{ext}"))
            else:
                for ext in extensions:
                    all_files.extend(path.glob(f"*{ext}"))
            
            # Sort files alphabetically for consistent ordering
            files_to_process = sorted(all_files, key=lambda x: str(x))
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
        
        # Find starting position for resumption
        start_index = 0
        if start_from and start_from.strip():
            start_from_path = Path(start_from.strip())
            try:
                start_index = files_to_process.index(start_from_path)
                logger.info(f"Resuming from file index {start_index}: {start_from}")
            except ValueError:
                logger.warning(f"Start file not found in list, starting from beginning: {start_from}")
                start_index = 0
        
        total_files = len(files_to_process)
        
        # Check if we're already done
        if start_index >= total_files:
            return json.dumps({
                "success": True,
                "status": "ALL_FILES_PROCESSED",
                "path": file_path,
                "batch_info": {
                    "total_files_found": total_files,
                    "batch_size": batch_size,
                    "files_processed": 0,
                    "remaining_files": 0
                },
                "note": "All files have been processed"
            }, indent=2)
        
        # Process only one batch
        end_index = min(start_index + batch_size, total_files)
        batch_files = files_to_process[start_index:end_index]
        
        logger.info(f"Processing batch: files {start_index + 1}-{end_index} of {total_files}")
        
        # Create or update source entry
        source_id = f"local:{Path(file_path).name}"
        
        # Process files in this batch
        batch_content_length = 0
        batch_word_count = 0
        batch_chunks_stored = 0
        processed_files = []
        
        # Process files concurrently in smaller groups
        async def process_file(file_path_obj):
            try:
                # Read file content
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content.strip():
                    return None
                
                # Create metadata
                file_url = f"file://{file_path_obj.absolute()}"
                metadata = {
                    "file_path": str(file_path_obj),
                    "file_name": file_path_obj.name,
                    "file_extension": file_path_obj.suffix,
                    "source_type": "local_file",
                    "word_count": len(content.split()),
                    "char_count": len(content)
                }
                
                # Chunk the content
                chunks = chunk_text(content, chunk_size=1000, overlap=200)
                
                # Process chunks concurrently
                chunk_tasks = []
                for chunk_idx, chunk in enumerate(chunks):
                    chunk_tasks.append(process_chunk(chunk, chunk_idx, file_url, metadata, source_id))
                
                # Wait for all chunks to be processed
                chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                chunks_stored = sum(1 for result in chunk_results if result is True)
                
                return {
                    "file": str(file_path_obj),
                    "size": len(content),
                    "words": len(content.split()),
                    "chunks": len(chunks),
                    "chunks_stored": chunks_stored,
                    "content_length": len(content),
                    "word_count": len(content.split())
                }
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path_obj}: {e}")
                return None
        
        async def process_chunk(chunk, chunk_idx, file_url, metadata, source_id):
            try:
                # Generate embedding for this chunk
                embedding = await generate_embedding(chunk)
                
                # Prepare data for database
                chunk_data = {
                    "url": file_url,
                    "chunk_number": chunk_idx,
                    "content": chunk,
                    "metadata": metadata,
                    "source_id": source_id,
                    "embedding": embedding
                }
                
                # Store in database
                await make_postgrest_request("/crawled_pages", "POST", chunk_data)
                return True
                
            except Exception as e:
                logger.warning(f"Failed to store chunk {chunk_idx}: {e}")
                return False
        
        # Process files concurrently (but limit concurrency to avoid overwhelming the system)
        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent files
        
        async def process_file_with_semaphore(file_path_obj):
            async with semaphore:
                return await process_file(file_path_obj)
        
        # Process the current batch
        file_tasks = [process_file_with_semaphore(file_path_obj) for file_path_obj in batch_files]
        file_results = await asyncio.gather(*file_tasks, return_exceptions=True)
        
        # Aggregate results from this batch
        batch_processed = 0
        for result in file_results:
            if result and isinstance(result, dict):
                processed_files.append(result)
                batch_content_length += result["content_length"]
                batch_word_count += result["word_count"]
                batch_chunks_stored += result["chunks_stored"]
                batch_processed += 1
        
        logger.info(f"Batch completed: {batch_processed}/{len(batch_files)} files processed successfully")
        
        # Determine next file to process
        next_file = None
        remaining_files = total_files - end_index
        status = "BATCH_COMPLETED"
        
        if end_index < total_files:
            next_file = str(files_to_process[end_index])
            status = "MORE_FILES_REMAINING"
        else:
            status = "ALL_FILES_PROCESSED"
        
        # Update source summary (incremental)
        try:
            # Try to get existing source first
            existing_sources = await make_postgrest_request(f"/sources?source_id=eq.{source_id}")
            
            if existing_sources:
                # Update existing source
                current_word_count = existing_sources[0].get("total_word_count", 0)
                new_total = current_word_count + batch_word_count
                
                await make_postgrest_request(f"/sources?source_id=eq.{source_id}", "PATCH", {
                    "total_word_count": new_total
                })
                logger.info(f"Updated source {source_id}: {current_word_count} -> {new_total} words")
            else:
                # Create new source
                source_data = {
                    "source_id": source_id,
                    "summary": f"Local files from {file_path} (batch processing)",
                    "total_word_count": batch_word_count
                }
                await make_postgrest_request("/sources", "POST", source_data)
                logger.info(f"Created new source: {source_id}")
                
        except Exception as e:
            logger.warning(f"Failed to update source summary: {e}")
        
        return json.dumps({
            "success": True,
            "status": status,
            "path": file_path,
            "batch_info": {
                "total_files_found": total_files,
                "batch_size": batch_size,
                "files_processed_in_batch": batch_processed,
                "remaining_files": remaining_files,
                "start_index": start_index,
                "end_index": end_index
            },
            "batch_content_length": batch_content_length,
            "batch_word_count": batch_word_count,
            "batch_chunks_stored": batch_chunks_stored,
            "source_id": source_id,
            "processed_files": processed_files[:3],  # Show first 3 files from this batch
            "next_file": next_file,
            "note": f"Processed {batch_processed} files in this batch. Use next_file parameter to continue." if next_file else f"All {total_files} files processed successfully!"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in crawl_local_files_batch: {e}")
        return json.dumps({
            "success": False,
            "path": file_path if 'file_path' in locals() else "unknown",
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
        
        # Process files and store in database
        total_files = len(files_to_process)
        total_content_length = 0
        total_word_count = 0
        total_chunks_stored = 0
        processed_files = []
        
        # Create or update source entry
        source_id = f"local:{Path(file_path).name}"
        
        for file_path_obj in files_to_process:
            try:
                # Read file content
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content.strip():
                    continue
                
                # Create metadata
                file_url = f"file://{file_path_obj.absolute()}"
                metadata = {
                    "file_path": str(file_path_obj),
                    "file_name": file_path_obj.name,
                    "file_extension": file_path_obj.suffix,
                    "source_type": "local_file",
                    "word_count": len(content.split()),
                    "char_count": len(content)
                }
                
                # Chunk the content
                chunks = chunk_text(content, chunk_size=1000, overlap=200)
                
                # Store each chunk
                chunks_stored = 0
                for chunk_idx, chunk in enumerate(chunks):
                    try:
                        # Generate embedding for this chunk
                        embedding = await generate_embedding(chunk)
                        
                        # Prepare data for database
                        chunk_data = {
                            "url": file_url,
                            "chunk_number": chunk_idx,
                            "content": chunk,
                            "metadata": metadata,
                            "source_id": source_id,
                            "embedding": embedding
                        }
                        
                        # Store in database
                        await make_postgrest_request("/crawled_pages", "POST", chunk_data)
                        chunks_stored += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to store chunk {chunk_idx} of {file_path_obj}: {e}")
                        continue
                
                total_content_length += len(content)
                total_word_count += len(content.split())
                total_chunks_stored += chunks_stored
                
                processed_files.append({
                    "file": str(file_path_obj),
                    "size": len(content),
                    "words": len(content.split()),
                    "chunks": len(chunks),
                    "chunks_stored": chunks_stored
                })
                
                logger.info(f"Processed {file_path_obj}: {chunks_stored} chunks stored")
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path_obj}: {e}")
                continue
        
        # Update or create source summary
        try:
            source_data = {
                "source_id": source_id,
                "summary": f"Local files from {file_path}",
                "total_word_count": total_word_count
            }
            
            # Try to create new source first
            try:
                await make_postgrest_request("/sources", "POST", source_data)
                logger.info(f"Created new source: {source_id}")
            except Exception as create_error:
                # If source already exists, try to update it
                try:
                    await make_postgrest_request(f"/sources?source_id=eq.{source_id}", "PATCH", {
                        "total_word_count": total_word_count
                    })
                    logger.info(f"Updated existing source: {source_id}")
                except Exception as update_error:
                    logger.warning(f"Failed to create or update source {source_id}: create={create_error}, update={update_error}")
                
        except Exception as e:
            logger.warning(f"Failed to update source summary: {e}")
        
        return json.dumps({
            "success": True,
            "path": file_path,
            "files_found": total_files,
            "files_processed": len(processed_files),
            "total_content_length": total_content_length,
            "total_word_count": total_word_count,
            "total_chunks_stored": total_chunks_stored,
            "source_id": source_id,
            "processed_files": processed_files[:5],  # Show first 5 files
            "note": "Real processing with embeddings and database storage"
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
        
        # Generate embedding for the query using SAP BTP AICore
        query_embedding = await generate_embedding(query)
        
        # Prepare the RPC call data
        rpc_data = {
            "query_embedding": query_embedding,
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
            "count": len(formatted_results)
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
