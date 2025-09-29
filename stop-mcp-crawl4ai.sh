#!/bin/bash

# MCP Crawl4AI RAG Server Stop Script
# This script stops the MCP server and all related Docker services

set -e  # Exit on any error

echo "🛑 Stopping MCP Crawl4AI RAG Server"
echo "===================================="

# Change to the project directory
# Intelligent directory detection (works from parent or project directory)
if [ -f "src/crawl4ai_mcp.py" ]; then
    echo "✅ Already in mcp-crawl4ai-rag directory"
else
    if [ -d "mcp-crawl4ai-rag" ]; then
        cd mcp-crawl4ai-rag
        echo "✅ Changed to mcp-crawl4ai-rag directory"
    else
        echo "❌ Error: Cannot find mcp-crawl4ai-rag directory or src/crawl4ai_mcp.py"
        exit 1
    fi
fi

# Function to stop MCP server processes
stop_mcp_server() {
    echo "🔍 Looking for MCP server processes..."
    
    # Find and kill MCP server processes (updated to match the correct module name)
    MCP_PIDS=$(pgrep -f "src.crawl4ai_mcp" 2>/dev/null || true)
    
    if [ -n "$MCP_PIDS" ]; then
        echo "🛑 Stopping MCP server processes: $MCP_PIDS"
        
        # First try graceful shutdown with SIGTERM
        echo "📤 Sending SIGTERM for graceful shutdown..."
        echo "$MCP_PIDS" | xargs kill -TERM 2>/dev/null || true
        
        # Wait longer for graceful shutdown (increased from 3 to 10 seconds)
        echo "⏳ Waiting 10 seconds for graceful shutdown..."
        sleep 10
        
        # Check if processes are still running
        MCP_PIDS=$(pgrep -f "src.crawl4ai_mcp" 2>/dev/null || true)
        if [ -n "$MCP_PIDS" ]; then
            echo "⚠️ Processes still running, trying SIGINT..."
            echo "$MCP_PIDS" | xargs kill -INT 2>/dev/null || true
            
            # Wait another 5 seconds
            echo "⏳ Waiting 5 more seconds..."
            sleep 5
            
            # Final check and force kill if necessary
            MCP_PIDS=$(pgrep -f "src.crawl4ai_mcp" 2>/dev/null || true)
            if [ -n "$MCP_PIDS" ]; then
                echo "⚠️ Force killing remaining MCP server processes: $MCP_PIDS"
                echo "$MCP_PIDS" | xargs kill -KILL 2>/dev/null || true
                
                # Final wait to ensure processes are gone
                sleep 2
            fi
        fi
        
        echo "✅ MCP server processes stopped"
    else
        echo "ℹ️ No MCP server processes found"
    fi
}

# Function to stop Docker services
stop_docker_services() {
    echo "🐳 Stopping Docker services..."
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "⚠️ Docker is not running, skipping Docker cleanup"
        return
    fi
    
    # Stop docker compose services
    if [ -f "docker compose.yml" ]; then
        echo "🗄️ Stopping docker compose services..."
        
        # Try both docker compose and docker compose commands
        if command -v docker compose > /dev/null 2>&1; then
            docker compose down 2>/dev/null || true
        elif docker compose version > /dev/null 2>&1; then
            docker compose down 2>/dev/null || true
        else
            echo "⚠️ Neither docker compose nor docker compose found"
        fi
        
        echo "✅ Docker services stopped"
    else
        echo "⚠️ docker compose.yml not found, skipping compose cleanup"
    fi
    
    # Stop any remaining containers related to the project
    echo "🔍 Looking for related Docker containers..."
    
    # Stop containers with names containing supabase, postgres, or postgrest
    RELATED_CONTAINERS=$(docker ps -q --filter "name=supabase" --filter "name=postgres" --filter "name=postgrest" 2>/dev/null || true)
    
    if [ -n "$RELATED_CONTAINERS" ]; then
        echo "🛑 Stopping related containers: $RELATED_CONTAINERS"
        echo "$RELATED_CONTAINERS" | xargs docker stop 2>/dev/null || true
        echo "✅ Related containers stopped"
    else
        echo "ℹ️ No related containers found running"
    fi
}

# Function to clean up volumes (optional)
cleanup_volumes() {
    echo ""
    read -p "Do you want to remove Docker volumes (this will delete all data)? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️ Removing Docker volumes..."
        
        # Remove project-specific volumes
        docker volume rm mcp-crawl4ai-rag_db_data 2>/dev/null || true
        
        # Remove any dangling volumes
        docker volume prune -f 2>/dev/null || true
        
        echo "✅ Docker volumes removed"
    else
        echo "ℹ️ Docker volumes preserved"
    fi
}

# Function to show running processes and containers
show_status() {
    echo ""
    echo "📊 Current Status:"
    echo "=================="
    
    # Check for MCP processes (updated to match the correct module name)
    MCP_PIDS=$(pgrep -f "src.crawl4ai_mcp" 2>/dev/null || true)
    if [ -n "$MCP_PIDS" ]; then
        echo "⚠️ MCP server processes still running: $MCP_PIDS"
    else
        echo "✅ No MCP server processes running"
    fi
    
    # Check for Docker containers
    if docker info > /dev/null 2>&1; then
        RUNNING_CONTAINERS=$(docker ps --filter "name=supabase" --filter "name=postgres" --filter "name=postgrest" --format "table {{.Names}}\t{{.Status}}" 2>/dev/null || true)
        
        if [ -n "$RUNNING_CONTAINERS" ] && [ "$RUNNING_CONTAINERS" != "NAMES	STATUS" ]; then
            echo "⚠️ Related Docker containers still running:"
            echo "$RUNNING_CONTAINERS"
        else
            echo "✅ No related Docker containers running"
        fi
    fi
}

# Main execution
echo "🚀 Starting shutdown process..."

# Stop MCP server
stop_mcp_server

# Stop Docker services
stop_docker_services

# Ask about volume cleanup
# cleanup_volumes

# Show final status
show_status

echo ""
echo "🎉 Shutdown complete!"
echo ""
echo "💡 Tips:"
echo "   - To start again, run: ../start-mcp-crawlai.sh"
echo "   - To check running processes: ps aux | grep crawl4ai_mcp"
echo "   - To check Docker containers: docker ps"
echo "   - To remove all Docker data: docker system prune -a --volumes"
echo ""
echo "👋 Goodbye!"
