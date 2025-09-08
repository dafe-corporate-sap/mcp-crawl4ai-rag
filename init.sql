-- Enable pgvector extension
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
