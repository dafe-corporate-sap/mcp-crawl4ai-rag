import json
import requests
import time
import sys
import os
import signal
from contextlib import contextmanager

def log_print(*args, **kwargs):
    print(*args, **kwargs)
    with open('mcp_client.log', 'a') as log_file:
        print(*args, **kwargs, file=log_file)

class MCPClient:
    def __init__(self, base_url="http://localhost:8051"):
        self.base_url = base_url
        self.session_id = None
        self.message_endpoint = None
        self.request_id = 0
        self.session = requests.Session()
        self.sse_response = None
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def close(self):
        """Clean up resources"""
        if self.sse_response:
            try:
                self.sse_response.close()
            except:
                pass
        if self.session:
            try:
                self.session.close()
            except:
                pass
        log_print("MCP client closed")
    
    def connect(self):
        """Establish SSE connection and get session info"""
        log_print("Connecting to MCP server...")
        
        try:
            # Connect to SSE endpoint
            sse_url = f"{self.base_url}/sse"
            headers = {"Accept": "text/event-stream"}
            
            self.sse_response = self.session.get(sse_url, headers=headers, stream=True, timeout=30)
            self.sse_response.raise_for_status()
            
            log_print(f"SSE connection established, status: {self.sse_response.status_code}")
            
            # Parse the first event to get endpoint info
            for line in self.sse_response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('event: endpoint'):
                        continue
                    elif line.startswith('data: '):
                        endpoint_data = line[6:]  # Remove 'data: '
                        self.message_endpoint = f"{self.base_url}{endpoint_data}"
                        # Extract session ID from endpoint
                        if 'session_id=' in endpoint_data:
                            self.session_id = endpoint_data.split('session_id=')[1]
                        log_print(f"Got message endpoint: {self.message_endpoint}")
                        break
            
            if not self.message_endpoint:
                raise Exception("Failed to get message endpoint from SSE")
                
            return True
            
        except Exception as e:
            log_print(f"Failed to connect: {e}")
            return False
    
    def send_message(self, message):
        """Send a message to the MCP server"""
        try:
            headers = {"Content-Type": "application/json"}
            response = self.session.post(self.message_endpoint, json=message, headers=headers, timeout=30)
            response.raise_for_status()
            log_print(f"Message sent successfully, status: {response.status_code}")
            return True
        except Exception as e:
            log_print(f"Failed to send message: {e}")
            return False
    
    def initialize(self):
        """Initialize the MCP session"""
        log_print("Initializing MCP session...")
        
        init_message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-client",
                    "version": "1.0.0"
                }
            }
        }
        
        if not self.send_message(init_message):
            return False
            
        self.request_id += 1
        
        # Send initialized notification
        initialized_message = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        
        return self.send_message(initialized_message)
    
    def call_tool(self, tool_name, arguments):
        """Call a tool on the MCP server"""
        log_print(f"Calling tool: {tool_name}")
        
        tool_message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        if not self.send_message(tool_message):
            return None
            
        self.request_id += 1
        return self.wait_for_response()
    
    def wait_for_response(self, timeout=300):
        """Wait for response from server with timeout"""
        log_print("Waiting for server response...")
        start_time = time.time()
        
        try:
            for line in self.sse_response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    
                    # Skip ping messages
                    if line.startswith(': ping'):
                        continue
                        
                    if line.startswith('event: message'):
                        continue
                    elif line.startswith('data: '):
                        try:
                            data = line[6:]  # Remove 'data: '
                            message = json.loads(data)
                            
                            # Check if this is a response to our request
                            if 'result' in message:
                                log_print("Received tool response")
                                return message['result']
                            elif 'error' in message:
                                log_print(f"Received error: {message['error']}")
                                return {"error": message['error']}
                                
                        except json.JSONDecodeError as e:
                            log_print(f"Failed to parse message: {e}")
                            continue
                
                # Check timeout
                if time.time() - start_time > timeout:
                    log_print("Timeout waiting for response")
                    return {"error": "Timeout waiting for response"}
                    
        except Exception as e:
            log_print(f"Error waiting for response: {e}")
            return {"error": f"Error waiting for response: {e}"}
        
        return {"error": "No response received"}

@contextmanager
def timeout_handler(seconds):
    """Context manager for handling timeouts"""
    def timeout_signal(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")
    
    # Set up signal handler
    old_handler = signal.signal(signal.SIGALRM, timeout_signal)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # Restore old handler and cancel alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def main():
    if len(sys.argv) < 2:
        log_print("Usage: python3 mcp_client.py <operation> [args]")
        log_print("Operations:")
        log_print("  get_available_sources")
        log_print("  delete_source <source_id>")
        log_print("  crawl_local_files <path>")
        log_print("  perform_rag_query <query> [source] [match_count]")
        sys.exit(1)

    operation = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []

    # Prepare tool arguments based on operation
    if operation == "delete_source":
        tool_name = "delete_source"
        tool_args = {"source_id": args[0]}
    elif operation == "crawl_local_files":
        log_print(f"Starting crawl_local_files operation for path: {args[0]}")
        tool_name = "crawl_local_files"
        tool_args = {
            "file_path": args[0],
            "recursive": True,
            "file_extensions": ".md,.txt,.html,.rst"
        }
        log_print(f"Tool arguments: {json.dumps(tool_args, indent=2)}")
    elif operation == "get_available_sources":
        tool_name = "get_available_sources"
        tool_args = {}
    elif operation == "perform_rag_query":
        if len(args) < 1:
            log_print("Error: perform_rag_query requires a query argument")
            sys.exit(1)
        tool_name = "perform_rag_query"
        tool_args = {
            "query": args[0],
            "source": args[1] if len(args) > 1 else None,
            "match_count": int(args[2]) if len(args) > 2 else 5
        }
    else:
        log_print(f"Unknown operation: {operation}")
        sys.exit(1)

    # Use timeout handler to prevent hanging
    try:
        with timeout_handler(600):  # 10 minute timeout
            with MCPClient() as client:
                # Connect to server
                if not client.connect():
                    log_print("Failed to connect to MCP server")
                    sys.exit(1)
                
                # Initialize session
                if not client.initialize():
                    log_print("Failed to initialize MCP session")
                    sys.exit(1)
                
                # Wait a moment for initialization to complete
                time.sleep(1)
                
                # Call the tool
                result = client.call_tool(tool_name, tool_args)
                
                if result:
                    if isinstance(result, dict) and 'content' in result:
                        # Handle tool response format
                        for content_item in result['content']:
                            if content_item['type'] == 'text':
                                try:
                                    # Try to parse as JSON for pretty printing
                                    parsed = json.loads(content_item['text'])
                                    log_print(json.dumps(parsed, indent=2))
                                except json.JSONDecodeError:
                                    # If not JSON, print as is
                                    log_print(content_item['text'])
                    else:
                        log_print(json.dumps(result, indent=2))
                else:
                    log_print("No result received from server")
                    
    except TimeoutError as e:
        log_print(f"Operation timed out: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        log_print("Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        log_print(f"Unexpected error: {e}")
        sys.exit(1)

    log_print("Script execution completed successfully.")

if __name__ == "__main__":
    main()
