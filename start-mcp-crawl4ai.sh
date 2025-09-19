#!/bin/bash

# MCP Crawl4AI RAG Server Startup Script
# This script sets up the local Supabase database and starts the MCP server

set -e  # Exit on any error

echo "🚀 Starting MCP Crawl4AI RAG Server with SAP BTP AICore"
echo "=================================================="

# Change to the project directory
# Check if we're already in the mcp-crawl4ai-rag directory
if [[ "$(basename "$(pwd)")" == "mcp-crawl4ai-rag" ]]; then
    echo "✅ Already in mcp-crawl4ai-rag directory"
else
    # Try to change to the project directory
    if [ -d "$(dirname "$0")/mcp-crawl4ai-rag" ]; then
        cd "$(dirname "$0")/mcp-crawl4ai-rag"
        echo "✅ Changed to mcp-crawl4ai-rag directory"
    elif [ -d "mcp-crawl4ai-rag" ]; then
        cd "mcp-crawl4ai-rag"
        echo "✅ Changed to mcp-crawl4ai-rag directory"
    else
        echo "❌ Error: mcp-crawl4ai-rag directory not found!"
        echo "Please run this script from the parent directory or from within mcp-crawl4ai-rag"
        exit 1
    fi
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.sap_btp_example to .env and configure your SAP BTP AICore credentials."
    exit 1
fi

# Load environment variables
source .env

# Check if required SAP BTP AICore variables are set
if [ -z "$SAP_BTP_AICORE_BASE_URL" ] || [ -z "$SAP_BTP_AICORE_CLIENT_ID" ]; then
    echo "❌ Error: SAP BTP AICore credentials not configured in .env file!"
    echo "Please configure SAP_BTP_AICORE_BASE_URL, SAP_BTP_AICORE_CLIENT_ID, and other required variables."
    exit 1
fi

echo "✅ Environment configuration loaded"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running!"
    echo "Please start Docker and try again."
    exit 1
fi

echo "✅ Docker is running"

# Check if local Supabase is already running
if docker ps | grep -q "supabase-postgres\|supabase-postgrest"; then
    echo "✅ Local Supabase is already running"
else
    echo "🗄️ Setting up local Supabase database..."
    
    # Run the local Supabase setup script
    if [ -f "setup_local_supabase.py" ]; then
        python3 setup_local_supabase.py
        echo "✅ Local Supabase database setup complete"
    else
        echo "❌ Error: setup_local_supabase.py not found!"
        exit 1
    fi
    
    # Wait a moment for services to fully start
    echo "⏳ Waiting for database services to start..."
    sleep 5
fi

# Test database connection
echo "🔍 Testing database connection..."
if python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
import httpx
import sys

try:
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if not url or not key:
        print('Database credentials not found')
        sys.exit(1)
    
    response = httpx.get(f'{url}/crawled_pages?select=count', 
                        headers={'apikey': key, 'Authorization': f'Bearer {key}'})
    
    if response.status_code == 200:
        print('Database connection successful')
    else:
        print(f'Database connection failed: {response.status_code}')
        sys.exit(1)
        
except Exception as e:
    print(f'Database test failed: {e}')
    sys.exit(1)
"; then
    echo "✅ Database connection verified"
else
    echo "❌ Database connection failed"
    exit 1
fi

# Test SAP BTP AICore connection
echo "🔍 Testing SAP BTP AICore connection..."
if python3 -c "
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path('.') / 'src'))

try:
    from sap_btp_aicore_client import get_aicore_client
    client = get_aicore_client()
    print('SAP BTP AICore client initialized successfully')
except Exception as e:
    print(f'SAP BTP AICore connection failed: {e}')
    sys.exit(1)
"; then
    echo "✅ SAP BTP AICore connection verified"
else
    echo "❌ SAP BTP AICore connection failed"
    exit 1
fi

# Start the MCP server
echo "🎯 Starting MCP server..."
echo "Server will be available on http://0.0.0.0:${PORT:-8051}"
echo "Press Ctrl+C to stop the server"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down MCP server..."
    
    # Ask user if they want to stop the database
    echo ""
    read -p "Do you want to stop the local Supabase database? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗄️ Stopping local Supabase database..."
        docker-compose down 2>/dev/null || docker compose down 2>/dev/null || echo "Database containers stopped"
        echo "✅ Local Supabase database stopped"
    else
        echo "ℹ️ Local Supabase database left running"
        echo "   Use 'docker-compose down' or 'docker compose down' to stop it later"
    fi
    
    echo "👋 Goodbye!"
}

# Set up cleanup trap
trap cleanup EXIT

# Start the MCP server (updated to use the correct module name)
python3 -m src.crawl4ai_mcp
