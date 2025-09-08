#!/usr/bin/env python3
"""
Script to set up Supabase database tables and functions for MCP Crawl4AI RAG server
"""
import os
import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_supabase_config():
    """Check if Supabase is configured"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        print("❌ Supabase not configured!")
        print("Please run: python update_supabase_config.py")
        return False
    
    print("✅ Supabase configuration found")
    print(f"   URL: {url}")
    print(f"   Key: {key[:20]}...")
    return True

def setup_database():
    """Set up the Supabase database"""
    try:
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        print("\n🔧 Connecting to Supabase...")
        supabase = create_client(url, key)
        
        # Test connection
        result = supabase.table('_test_connection').select('*').limit(1).execute()
        print("✅ Connected to Supabase successfully!")
        
        print("\n📋 Setting up database schema...")
        
        # SQL commands to execute
        sql_commands = [
            # Enable vector extension
            "CREATE EXTENSION IF NOT EXISTS vector;",
            
            # Create crawled_pages table
            """
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
            """,
            
            # Create sources table
            """
            CREATE TABLE IF NOT EXISTS sources (
                id BIGSERIAL PRIMARY KEY,
                source_id TEXT UNIQUE NOT NULL,
                summary TEXT,
                total_word_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            # Create code_examples table
            """
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
            """,
            
            # Create indexes
            "CREATE INDEX IF NOT EXISTS idx_crawled_pages_source_id ON crawled_pages(source_id);",
            "CREATE INDEX IF NOT EXISTS idx_crawled_pages_url ON crawled_pages(url);",
            "CREATE INDEX IF NOT EXISTS idx_sources_source_id ON sources(source_id);",
            "CREATE INDEX IF NOT EXISTS idx_code_examples_source_id ON code_examples(source_id);",
            "CREATE INDEX IF NOT EXISTS idx_code_examples_url ON code_examples(url);",
            
            # Create vector indexes (these might take a moment)
            "CREATE INDEX IF NOT EXISTS idx_crawled_pages_embedding ON crawled_pages USING ivfflat (embedding vector_cosine_ops);",
            "CREATE INDEX IF NOT EXISTS idx_code_examples_embedding ON code_examples USING ivfflat (embedding vector_cosine_ops);",
        ]
        
        # Execute SQL commands
        for i, sql in enumerate(sql_commands, 1):
            try:
                print(f"   [{i}/{len(sql_commands)}] Executing SQL command...")
                supabase.rpc('exec_sql', {'sql': sql}).execute()
                print(f"   ✅ Command {i} completed")
            except Exception as e:
                # Try alternative method for some commands
                if "exec_sql" in str(e):
                    print(f"   ⚠️  Command {i} needs manual execution (see SUPABASE_SETUP.md)")
                else:
                    print(f"   ❌ Command {i} failed: {e}")
        
        print("\n🔧 Creating search functions...")
        
        # Create search functions (these need to be done via SQL editor)
        functions_sql = """
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
        """
        
        # Save functions to file for manual execution
        with open("supabase_functions.sql", "w") as f:
            f.write(functions_sql)
        
        print("   📄 Search functions saved to 'supabase_functions.sql'")
        print("   ⚠️  Please execute this SQL in your Supabase SQL Editor")
        
        print("\n🧪 Testing database setup...")
        
        # Test tables exist
        tables_to_check = ['crawled_pages', 'sources', 'code_examples']
        for table in tables_to_check:
            try:
                result = supabase.table(table).select('count').limit(1).execute()
                print(f"   ✅ Table '{table}' exists and accessible")
            except Exception as e:
                print(f"   ❌ Table '{table}' issue: {e}")
        
        print("\n🎉 Database setup completed!")
        print("\n📋 Next steps:")
        print("1. Go to your Supabase dashboard → SQL Editor")
        print("2. Execute the SQL in 'supabase_functions.sql'")
        print("3. Run: python test_supabase_connection.py")
        
        return True
        
    except ImportError:
        print("❌ Supabase client not installed!")
        print("Run: pip install supabase")
        return False
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False

def main():
    """Main function"""
    print("🚀 Supabase Database Setup")
    print("=" * 40)
    
    # Check configuration
    if not check_supabase_config():
        return False
    
    # Setup database
    return setup_database()

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
