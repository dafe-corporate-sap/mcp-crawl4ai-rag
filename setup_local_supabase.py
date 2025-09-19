#!/usr/bin/env python3
"""
Script to set up local Supabase using Docker for MCP Crawl4AI RAG server
"""
import os
import sys
import subprocess
import time
from pathlib import Path

def check_docker():
    """Check if Docker is installed and running"""
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker is installed")
            print(f"   Version: {result.stdout.strip()}")
        else:
            print("❌ Docker not found")
            return False
        
        # Check if Docker daemon is running
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker daemon is running")
            return True
        else:
            print("❌ Docker daemon not running")
            print("   Please start Docker Desktop or Docker service")
            return False
            
    except FileNotFoundError:
        print("❌ Docker not installed")
        print("   Please install Docker Desktop from: https://www.docker.com/products/docker-desktop")
        return False

def create_docker_compose():
    """Create docker compose.yml for local Supabase"""
    compose_content = """version: '3.8'

services:
  # PostgreSQL database with pgvector extension
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  # PostgREST API server
  postgrest:
    image: postgrest/postgrest:v12.0.2
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      PGRST_DB_URI: postgres://postgres:postgres@db:5432/postgres
      PGRST_DB_SCHEMAS: public
      PGRST_DB_ANON_ROLE: anon
      PGRST_JWT_SECRET: super-secret-jwt-token-with-at-least-32-characters-long
    depends_on:
      db:
        condition: service_healthy

volumes:
  db_data:
"""
    
    with open("docker compose.yml", "w") as f:
        f.write(compose_content)
    
    print("✅ Created docker compose.yml")

def create_init_sql():
    """Create initialization SQL for the database"""
    init_sql = """-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create anon role for PostgREST
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgres';
GRANT anon TO authenticator;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO anon;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon;

-- Create crawled_pages table
CREATE TABLE IF NOT EXISTS crawled_pages (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    source_id TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create sources table
CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT UNIQUE NOT NULL,
    summary TEXT,
    total_word_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create code_examples table
CREATE TABLE IF NOT EXISTS code_examples (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    metadata JSONB,
    source_id TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_crawled_pages_source_id ON crawled_pages(source_id);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_url ON crawled_pages(url);
CREATE INDEX IF NOT EXISTS idx_sources_source_id ON sources(source_id);
CREATE INDEX IF NOT EXISTS idx_code_examples_source_id ON code_examples(source_id);
CREATE INDEX IF NOT EXISTS idx_code_examples_url ON code_examples(url);

-- Create vector indexes
CREATE INDEX IF NOT EXISTS idx_crawled_pages_embedding ON crawled_pages USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_code_examples_embedding ON code_examples USING ivfflat (embedding vector_cosine_ops);

-- Grant permissions on new tables
GRANT ALL ON crawled_pages TO anon;
GRANT ALL ON sources TO anon;
GRANT ALL ON code_examples TO anon;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon;

-- Function to search documents using vector similarity
CREATE OR REPLACE FUNCTION match_crawled_pages(
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5,
    filter JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE(
    id BIGINT,
    url TEXT,
    chunk_number INTEGER,
    content TEXT,
    metadata JSONB,
    source_id TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        cp.id,
        cp.url,
        cp.chunk_number,
        cp.content,
        cp.metadata,
        cp.source_id,
        1 - (cp.embedding <=> query_embedding) AS similarity
    FROM crawled_pages cp
    WHERE (
        filter = '{}'::jsonb OR
        (filter ? 'source' AND cp.source_id = (filter->>'source'))
    )
    ORDER BY cp.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to search code examples using vector similarity
CREATE OR REPLACE FUNCTION match_code_examples(
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5,
    filter JSONB DEFAULT '{}'::jsonb,
    source_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    id BIGINT,
    url TEXT,
    chunk_number INTEGER,
    content TEXT,
    summary TEXT,
    metadata JSONB,
    source_id TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ce.id,
        ce.url,
        ce.chunk_number,
        ce.content,
        ce.summary,
        ce.metadata,
        ce.source_id,
        1 - (ce.embedding <=> query_embedding) AS similarity
    FROM code_examples ce
    WHERE (
        (filter = '{}'::jsonb OR
         (filter ? 'source' AND ce.source_id = (filter->>'source'))) AND
        (source_filter IS NULL OR ce.source_id = source_filter)
    )
    ORDER BY ce.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Grant execute permissions on functions
GRANT EXECUTE ON FUNCTION match_crawled_pages TO anon;
GRANT EXECUTE ON FUNCTION match_code_examples TO anon;
"""
    
    with open("init.sql", "w") as f:
        f.write(init_sql)
    
    print("✅ Created init.sql")

def update_env_for_local():
    """Update .env file for local Supabase"""
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env file not found!")
        return False
    
    # Read current .env file
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update the lines
    updated_lines = []
    supabase_url_updated = False
    supabase_key_updated = False
    
    for line in lines:
        if line.startswith("SUPABASE_URL="):
            updated_lines.append("SUPABASE_URL=http://localhost:3000\n")
            supabase_url_updated = True
        elif line.startswith("SUPABASE_SERVICE_KEY="):
            # Generate proper JWT token for local PostgREST
            import jwt
            from datetime import datetime, timedelta
            
            jwt_secret = "super-secret-jwt-token-with-at-least-32-characters-long"
            payload = {
                "role": "anon",
                "iat": int(datetime.now().timestamp()),
                "exp": int((datetime.now() + timedelta(days=365)).timestamp())
            }
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            updated_lines.append(f"SUPABASE_SERVICE_KEY={token}\n")
            supabase_key_updated = True
        else:
            updated_lines.append(line)
    
    # Add missing lines if not found
    if not supabase_url_updated:
        updated_lines.append("SUPABASE_URL=http://localhost:3000\n")
    if not supabase_key_updated:
        # Generate proper JWT token for local PostgREST
        import jwt
        from datetime import datetime, timedelta
        
        jwt_secret = "super-secret-jwt-token-with-at-least-32-characters-long"
        payload = {
            "role": "anon",
            "iat": int(datetime.now().timestamp()),
            "exp": int((datetime.now() + timedelta(days=365)).timestamp())
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        updated_lines.append(f"SUPABASE_SERVICE_KEY={token}\n")
    
    # Write back to file
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print("✅ Updated .env file for local Supabase")
    return True

def start_services():
    """Start the Docker services"""
    print("\n🚀 Starting local Supabase services...")
    
    try:
        # Start services
        result = subprocess.run(['docker', 'compose', 'up', '-d'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Services started successfully")
        else:
            print(f"❌ Failed to start services: {result.stderr}")
            return False
        
        # Wait for services to be ready
        print("⏳ Waiting for services to be ready...")
        time.sleep(10)
        
        # Check if services are running
        result = subprocess.run(['docker', 'compose', 'ps'], capture_output=True, text=True)
        print("📋 Service status:")
        print(result.stdout)
        
        return True
        
    except FileNotFoundError:
        print("❌ docker compose not found")
        print("   Please install Docker Compose")
        return False

def test_local_connection():
    """Test connection to local Supabase"""
    print("\n🧪 Testing local Supabase connection...")
    
    try:
        import requests
        
        # Test PostgREST API
        response = requests.get("http://localhost:3000/", timeout=5)
        if response.status_code == 200:
            print("✅ PostgREST API is responding")
        else:
            print(f"❌ PostgREST API error: {response.status_code}")
            return False
        
        # Test database tables
        response = requests.get("http://localhost:3000/crawled_pages?limit=1", timeout=5)
        if response.status_code == 200:
            print("✅ Database tables accessible")
        else:
            print(f"❌ Database tables error: {response.status_code}")
            return False
        
        return True
        
    except ImportError:
        print("⚠️  requests not installed, skipping HTTP test")
        return True
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def main():
    """Main function"""
    print("🚀 Local Supabase Setup")
    print("=" * 40)
    
    # Check Docker
    if not check_docker():
        return False
    
    # Create configuration files
    print("\n📋 Creating configuration files...")
    create_docker_compose()
    create_init_sql()
    
    # Update environment
    if not update_env_for_local():
        return False
    
    # Start services
    if not start_services():
        return False
    
    # Test connection
    if not test_local_connection():
        print("⚠️  Services started but connection test failed")
        print("   This might be normal - services may need more time to initialize")
    
    print("\n🎉 Local Supabase setup completed!")
    print("\n📋 Service URLs:")
    print("   Database: postgresql://postgres:postgres@localhost:5433/postgres")
    print("   API: http://localhost:3000")
    print("\n🔧 Management commands:")
    print("   Stop services: docker compose down")
    print("   View logs: docker compose logs")
    print("   Restart: docker compose restart")
    
    print("\n🧪 Test the setup:")
    print("   python test_local_supabase.py")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
