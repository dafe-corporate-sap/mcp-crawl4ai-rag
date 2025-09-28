"""
MCP server that works directly with PostgREST API instead of Supabase client.

This version bypasses the Supabase client and makes direct HTTP requests to PostgREST.
"""
import asyncio
import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from sap_btp_aicore_client import SAPBTPAICoreClient

try:
    import aiohttp
    from aiohttp import web
except ImportError:
    print("Error: aiohttp module not found. Please install it using 'pip install aiohttp'.")
    sys.exit(1)

# Load environment variables
load_dotenv()

# AI Core configuration
AI_CORE_URL = os.getenv("AI_CORE_URL")
AI_CORE_API_KEY = os.getenv("AI_CORE_API_KEY")
AI_CORE_RESOURCE_GROUP = os.getenv("AI_CORE_RESOURCE_GROUP")
AI_CORE_DEPLOYMENT_ID = os.getenv("AI_CORE_DEPLOYMENT_ID")

# Initialize AI Core client
ai_core_client = SAPBTPAICoreClient()

async def get_embedding(text: str) -> List[float]:
    """
    Get embedding for the given text using SAP BTP AI Core.
    
    Args:
        text: The text to get embedding for
    
    Returns:
        List of floats representing the embedding
    """
    try:
        response = ai_core_client.create_embeddings([text])
        return response.embeddings[0]
    except Exception as e:
        logger.error(f"Error getting embedding from AI Core: {e}")
        raise

# Import MCP components
from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

####################################################################################
# Enhanced monkeypatch for session management and error logging
# pylint: disable-next=protected-access
old__received_request = ServerSession._received_request

async def _received_request(self, *args, **kwargs):
    try:
        session_id = getattr(self, 'session_id', 'unknown')
        logger.debug(f"Received request for session {session_id}")
        logger.debug(f"Request args: {args}")
        logger.debug(f"Request kwargs: {kwargs}")
        
        if not hasattr(self, 'initialized'):
            logger.info(f"Initializing session {session_id}")
            await self.initialize()
            self.initialized = True
            logger.info(f"Session {session_id} initialized successfully")
        
        return await old__received_request(self, *args, **kwargs)
    except Exception as e:
        logger.error(f"Error processing request for session {session_id}: {str(e)}")
        raise

async def initialize(self):
    # Add any initialization logic here
    pass

async def _cleanup_session(self):
    try:
        session_id = getattr(self, 'session_id', 'unknown')
        logger.info(f"Cleaning up session {session_id}")
        # Add any necessary cleanup logic here
        logger.info(f"Session {session_id} cleaned up successfully")
    except Exception as e:
        logger.error(f"Error cleaning up session {session_id}: {str(e)}")

# Monkey-patch the initialize and cleanup methods
ServerSession.initialize = initialize
ServerSession.cleanup = _cleanup_session

# Apply the enhanced monkeypatch
# pylint: disable-next=protected-access
ServerSession._received_request = _received_request
####################################################################################

# PostgREST configuration
POSTGREST_URL = os.getenv("SUPABASE_URL", "http://localhost:3000")
POSTGREST_TOKEN = os.getenv("SUPABASE_SERVICE_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("mcp-crawl4ai-rag-postgrest")

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
                        # Handle cases where 201 Created might return empty response
                        try:
                            response_text = await response.text()
                            if response_text.strip():
                                return await response.json()
                            else:
                                # Empty response is OK for 201 Created
                                return {"status": "created", "code": 201}
                        except Exception as json_error:
                            # If JSON parsing fails but status is success, return status info
                            if response.status == 201:
                                return {"status": "created", "code": 201}
                            else:
                                raise json_error
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
            elif method == "DELETE":
                async with session.delete(url, headers=headers) as response:
                    if response.status in [200, 204]:  # Accept 200 OK and 204 No Content
                        if response.status == 204:
                            return {}  # No content response
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
            elif method == "PATCH":
                async with session.patch(url, headers=headers, json=data) as response:
                    if response.status in [200, 204]:  # Accept 200 OK and 204 No Content
                        if response.status == 204:
                            return {}  # No content response
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
        
        # Import required modules (avoid supabase client dependency)
        from pathlib import Path
        from urllib.parse import urlparse
        import sys
        import os
        
        # Add src directory to path for imports
        src_path = os.path.join(os.path.dirname(__file__))
        if src_path not in sys.path:
            sys.path.append(src_path)
        
        # Validate file path
        if not file_path or not file_path.strip():
            return json.dumps({
                "success": False,
                "error": "File path cannot be empty"
            }, indent=2)
        
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
        
        logger.info(f"Found {len(files_to_process)} files to process")
        
        # Process files and prepare data for database storage
        urls = []
        chunk_numbers = []
        contents = []
        metadatas = []
        url_to_full_document = {}
        
        total_files = len(files_to_process)
        total_content_length = 0
        total_word_count = 0
        processed_files = []
        failed_files = []
        
        for i, file_path_obj in enumerate(files_to_process):
            try:
                # Log progress for large datasets
                if total_files > 100 and (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1}/{total_files} files...")
                
                # Read file content
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Skip empty files
                if not content.strip():
                    continue
                
                # Create file URL and metadata
                file_url = f"file://{file_path_obj.absolute()}"
                
                # Chunk content (simple chunking - split by paragraphs or every 1000 chars)
                chunks = []
                if len(content) <= 1000:
                    chunks = [content]
                else:
                    # Split by double newlines first (paragraphs)
                    paragraphs = content.split('\n\n')
                    current_chunk = ""
                    
                    for paragraph in paragraphs:
                        if len(current_chunk + paragraph) <= 1000:
                            current_chunk += paragraph + '\n\n'
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = paragraph + '\n\n'
                    
                    # Add remaining content
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                
                # Store full document for contextual embeddings
                url_to_full_document[file_url] = content
                
                # Add chunks to processing lists
                for chunk_num, chunk in enumerate(chunks):
                    urls.append(file_url)
                    chunk_numbers.append(chunk_num)
                    contents.append(chunk)
                    metadatas.append({
                        "file_path": str(file_path_obj),
                        "file_name": file_path_obj.name,
                        "file_extension": file_path_obj.suffix,
                        "chunk_index": chunk_num,
                        "total_chunks": len(chunks)
                    })
                
                total_content_length += len(content)
                total_word_count += len(content.split())
                
                processed_files.append({
                    "file": str(file_path_obj),
                    "size": len(content),
                    "words": len(content.split()),
                    "chunks": len(chunks)
                })
                
            except Exception as e:
                logger.warning(f"Failed to process file {file_path_obj}: {e}")
                failed_files.append(str(file_path_obj))
                continue
        
        logger.info(f"Prepared {len(contents)} chunks from {len(processed_files)} files for database storage")
        
        # Store in database using direct PostgREST API calls
        if contents:
            # First, delete existing records for these URLs
            unique_urls = list(set(urls))
            for url in unique_urls:
                try:
                    await make_postgrest_request(f"/crawled_pages?url=eq.{url}", "DELETE")
                except Exception as e:
                    logger.warning(f"Failed to delete existing records for {url}: {e}")
            
            # Store documents in batches
            batch_size = 10  # Smaller batch size for better reliability
            stored_chunks = 0
            failed_chunks = 0
            
            # Determine consistent source_id based on the input path
            if path.is_file():
                # For single files, use the parent directory name to match directory processing
                main_source_id = f"local:{path.parent.name}"
            else:  
                # For directories, use the directory name
                main_source_id = f"local:{path.name}"
            
            logger.info(f"Using consistent source_id: {main_source_id} for path: {file_path}")
            
            for i in range(0, len(contents), batch_size):
                batch_end = min(i + batch_size, len(contents))
                
                # Prepare batch data
                batch_data = []
                for j in range(i, batch_end):
                    # Generate embedding using SAP BTP AICore
                    try:
                        embedding = await get_embedding(contents[j])
                    except Exception as e:
                        logger.error(f"Failed to get embedding for chunk {j}: {e}")
                        embedding = None  # or some default value
                    
                    batch_data.append({
                        "url": urls[j],
                        "chunk_number": chunk_numbers[j],
                        "content": contents[j],
                        "metadata": metadatas[j],
                        "source_id": main_source_id,  # Use consistent source_id
                        "embedding": embedding
                    })
                
                # Insert batch with proper error handling
                try:
                    result = await make_postgrest_request("/crawled_pages", "POST", batch_data)
                    stored_chunks += len(batch_data)
                    logger.info(f"Successfully stored batch {i//batch_size + 1}/{(len(contents) + batch_size - 1) // batch_size}, chunks stored: {len(batch_data)}, total: {stored_chunks}")
                except Exception as e:
                    error_str = str(e).lower()
                    # PostgREST returns 201 Created for successful inserts, which might not have JSON response
                    if "201" in error_str or "created" in error_str:
                        stored_chunks += len(batch_data)
                        logger.info(f"Successfully stored batch {i//batch_size + 1} (HTTP 201 Created), chunks: {len(batch_data)}, total: {stored_chunks}")
                    else:
                        failed_chunks += len(batch_data)
                        logger.error(f"Failed to store batch {i//batch_size + 1}: {e}")
                        # Continue with next batch instead of failing completely
            
            # Create or update source entry with detailed debugging using consistent source_id
            source_created = False
            # Use the same source_id logic as for chunks
            if path.is_file():
                source_id = f"local:{path.parent.name}"
            else:
                source_id = f"local:{path.name}"
            
            summary = f"Local files from {file_path} containing {total_word_count} words"
            
            logger.info(f"Starting source creation process for: {source_id}")
            
            try:
                # First check if source exists
                logger.info(f"Checking if source exists: {source_id}")
                existing_sources = await make_postgrest_request(f"/sources?source_id=eq.{source_id}")
                logger.info(f"Existing sources query result: {existing_sources}")
                
                if existing_sources and len(existing_sources) > 0:
                    # Update existing source
                    logger.info(f"Updating existing source: {source_id}")
                    source_data = {
                        "summary": summary,
                        "total_word_count": total_word_count
                    }
                    result = await make_postgrest_request(f"/sources?source_id=eq.{source_id}", "PATCH", source_data)
                    logger.info(f"PATCH result: {result}")
                    source_created = True
                    logger.info(f"Successfully updated existing source: {source_id}")
                else:
                    # Create new source
                    logger.info(f"Creating new source: {source_id}")
                    source_data = {
                        "source_id": source_id,
                        "summary": summary,
                        "total_word_count": total_word_count
                    }
                    logger.info(f"Source data to create: {source_data}")
                    
                    result = await make_postgrest_request("/sources", "POST", source_data)
                    logger.info(f"POST result: {result}")
                    
                    # Check if the result indicates success (either has data or is HTTP 201)
                    if result and (result.get("status") == "created" or result.get("code") == 201):
                        source_created = True
                        logger.info(f"Successfully created new source: {source_id} (HTTP 201)")
                    elif result:
                        source_created = True
                        logger.info(f"Successfully created new source: {source_id} (with data)")
                    else:
                        logger.warning(f"Unexpected result from source creation: {result}")
                        
            except Exception as e:
                logger.error(f"Exception during source creation for {source_id}: {str(e)}")
                logger.error(f"Exception type: {type(e).__name__}")
                # Check if it's actually a success case that's being treated as an error
                error_str = str(e).lower()
                if "201" in error_str or "created" in error_str:
                    logger.info(f"Source creation succeeded despite exception (HTTP 201): {source_id}")
                    source_created = True
                else:
                    source_created = False
            
            # Final verification - check if source exists in database
            try:
                verification_result = await make_postgrest_request(f"/sources?source_id=eq.{source_id}")
                if verification_result and len(verification_result) > 0:
                    logger.info(f"Source verification successful: {source_id} exists in database")
                    source_created = True
                else:
                    logger.error(f"Source verification failed: {source_id} not found in database")
                    source_created = False
            except Exception as verify_e:
                logger.error(f"Source verification error: {verify_e}")
            
            if source_created:
                logger.info(f"✅ Source creation completed successfully: {source_id}")
            else:
                logger.error(f"❌ Source creation failed: {source_id}")
                return json.dumps({
                    "success": False,
                    "path": file_path,
                    "error": f"Failed to create source entry for {source_id}. Chunks were stored but source is missing.",
                    "chunks_stored": len(contents),
                    "source_creation_failed": True
                }, indent=2)
        
        logger.info(f"Successfully processed and stored {len(processed_files)} files")
        
        return json.dumps({
            "success": True,
            "path": file_path,
            "files_found": total_files,
            "files_processed": len(processed_files),
            "files_failed": len(failed_files),
            "total_content_length": total_content_length,
            "total_word_count": total_word_count,
            "total_chunks_stored": len(contents),
            "processed_files": processed_files[:5],  # Show first 5 files
            "failed_files": failed_files[:5] if failed_files else [],  # Show first 5 failed files
            "note": "Files processed and stored in database with embeddings"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in crawl_local_files: {e}")
        return json.dumps({
            "success": False,
            "path": file_path if 'file_path' in locals() else "unknown",
            "error": f"Error: {str(e)}"
        }, indent=2)

@mcp.tool()
async def delete_source(source_id: str) -> str:
    """
    Delete a source and all its associated content from the database.
    
    This tool removes a source and all crawled pages/code examples associated with it.
    Use with caution as this operation cannot be undone.
    
    Args:
        source_id: The source ID to delete (e.g., 'local:CPMSCF-docs', 'help.sap.com')
    
    Returns:
        JSON string with deletion summary
    """
    try:
        logger.info(f"delete_source called with source_id: '{source_id}'")
        
        # Validate source_id
        if not source_id or not source_id.strip():
            return json.dumps({
                "success": False,
                "error": "Source ID cannot be empty"
            }, indent=2)
        
        source_id = source_id.strip()
        
        # Check if source exists
        try:
            sources = await make_postgrest_request(f"/sources?source_id=eq.{source_id}")
            if not sources:
                return json.dumps({
                    "success": False,
                    "error": f"Source '{source_id}' not found"
                }, indent=2)
        except Exception as e:
            logger.error(f"Error checking source existence: {e}")
            return json.dumps({
                "success": False,
                "error": f"Error checking source: {str(e)}"
            }, indent=2)
        
        deleted_items = {
            "crawled_pages": 0,
            "code_examples": 0,
            "source": 0
        }
        
        # Delete crawled_pages for this source
        try:
            await make_postgrest_request(f"/crawled_pages?source_id=eq.{source_id}", "DELETE")
            deleted_items["crawled_pages"] = "deleted"
            logger.info(f"Deleted crawled_pages for source: {source_id}")
        except Exception as e:
            logger.warning(f"Failed to delete crawled_pages for {source_id}: {e}")
        
        # Delete code_examples for this source (if table exists)
        try:
            await make_postgrest_request(f"/code_examples?source_id=eq.{source_id}", "DELETE")
            deleted_items["code_examples"] = "deleted"
            logger.info(f"Deleted code_examples for source: {source_id}")
        except Exception as e:
            logger.warning(f"Failed to delete code_examples for {source_id}: {e}")
        
        # Delete the source itself
        try:
            await make_postgrest_request(f"/sources?source_id=eq.{source_id}", "DELETE")
            deleted_items["source"] = "deleted"
            logger.info(f"Deleted source: {source_id}")
        except Exception as e:
            logger.error(f"Failed to delete source {source_id}: {e}")
            return json.dumps({
                "success": False,
                "source_id": source_id,
                "error": f"Failed to delete source: {str(e)}",
                "partial_cleanup": deleted_items
            }, indent=2)
        
        logger.info(f"Successfully deleted source: {source_id}")
        return json.dumps({
            "success": True,
            "source_id": source_id,
            "deleted_items": deleted_items,
            "message": f"Source '{source_id}' and all associated content successfully deleted"
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error in delete_source: {e}")
        return json.dumps({
            "success": False,
            "source_id": source_id if 'source_id' in locals() else "unknown",
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
        try:
            query_embedding = await get_embedding(query)
        except Exception as e:
            logger.error(f"Failed to get embedding for query: {e}")
            return json.dumps({
                "success": False,
                "error": f"Failed to generate embedding for query: {str(e)}"
            }, indent=2)
        
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
        logger.info(f"Server will be available on http://0.0.0.0:8051")
        
        # Add more detailed logging
        logger.debug("MCP server configuration:")
        logger.debug(f"POSTGREST_URL: {POSTGREST_URL}")
        logger.debug(f"AI Core URL: {AI_CORE_URL}")
        
        # Test PostgREST connection
        try:
            await make_postgrest_request("/sources", "GET")
            logger.info("Successfully connected to PostgREST")
        except Exception as postgrest_error:
            logger.error(f"Failed to connect to PostgREST: {postgrest_error}")
        
        # Test AI Core connection
        try:
            await get_embedding("Test embedding")
            logger.info("Successfully connected to SAP BTP AICore")
        except Exception as aicore_error:
            logger.error(f"Failed to connect to SAP BTP AICore: {aicore_error}")
        
        await mcp.run_sse_async()
        
    except KeyboardInterrupt:
        logger.info("Shutting down MCP server...")
    except Exception as e:
        logger.error(f"Fatal error in MCP server: {e}")
        raise

# Add a new function to handle incoming connections
async def handle_connection(request):
    client_host = request.client.host
    logger.info(f"Incoming connection from {client_host}")
    try:
        # Process the request
        response = await mcp.handle_request(request)
        logger.info(f"Successfully processed request from {client_host}")
        return response
    except Exception as e:
        logger.error(f"Error processing request from {client_host}: {str(e)}")
        # Instead of re-raising the exception, return an error response
        return aiohttp.web.json_response({"error": "Internal server error"}, status=500)

async def start_server():
    app = web.Application()
    app.router.add_route('*', '/{tail:.*}', handle_connection)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8051)
    await site.start()
    logger.info("Server started on http://0.0.0.0:8051")
    return runner, site

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
