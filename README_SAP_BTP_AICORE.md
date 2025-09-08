# MCP Crawl4AI RAG Server with SAP BTP AICore Integration

This is an adapted version of the mcp-crawl4ai-rag server that uses **SAP BTP AICore** instead of OpenAI for embeddings and chat completions. This integration allows you to leverage SAP's AI services while maintaining all the original functionality of the RAG server.

## 🚀 Key Features

- **SAP BTP AICore Integration**: Uses SAP BTP AICore for embeddings and chat completions instead of OpenAI
- **Orchestration Service Support**: Supports both direct AI Core services and the Orchestration service
- **Automatic Token Management**: Handles OAuth2 authentication and token refresh automatically
- **Fallback Mechanisms**: Robust error handling with retry logic and fallback strategies
- **Full RAG Functionality**: All original features including web crawling, vector search, and knowledge graphs

## 📋 Prerequisites

1. **SAP BTP AICore Service**: Access to SAP BTP AICore with appropriate service plans
2. **Service Key**: A service key for your AI Core service instance
3. **Deployments**: Either pre-configured deployments or the ability to create them automatically
4. **Supabase**: A Supabase project for vector storage (unchanged from original)

## 🛠️ Setup Instructions

### 1. SAP BTP AICore Configuration

#### Option A: Using Existing Deployments
If you already have deployments configured in SAP BTP AICore:

1. Get your service key from SAP BTP Cockpit
2. Note down your deployment URLs from AI Launchpad
3. Configure environment variables with deployment URLs

#### Option B: Automatic Deployment Creation
The server can automatically create deployments if they don't exist:

1. Get your service key from SAP BTP Cockpit
2. Ensure you have the necessary permissions to create configurations and deployments
3. Leave deployment ID environment variables empty for auto-creation

### 2. Environment Configuration

Copy the example environment file:
```bash
cp .env.sap_btp_example .env
```

Edit `.env` with your actual values:

```bash
# SAP BTP AICore Authentication (from your service key)
SAP_BTP_AICORE_BASE_URL=https://api.ai.ml.hana.ondemand.com
SAP_BTP_AICORE_AUTH_URL=https://your-subdomain.authentication.eu10.hana.ondemand.com
SAP_BTP_AICORE_CLIENT_ID=your-client-id
SAP_BTP_AICORE_CLIENT_SECRET=your-client-secret
SAP_BTP_AICORE_RESOURCE_GROUP=default

# Optional: Specify deployment IDs if you have existing deployments
SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID=your-orchestration-deployment-id
# OR specify individual service deployments
SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID=your-embedding-deployment-id
SAP_BTP_AICORE_CHAT_DEPLOYMENT_ID=your-chat-deployment-id

# Model Configuration
SAP_BTP_AICORE_EMBEDDING_MODEL=text-embedding-3-large
SAP_BTP_AICORE_CHAT_MODEL=gpt-4o

# Supabase Configuration (unchanged)
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_KEY=your-supabase-service-key
```

### 3. Installation

Install Python dependencies:
```bash
pip install -r requirements.txt
```

### 4. Running the Server

Start the MCP server:
```bash
python src/crawl4ai_mcp.py
```

The server will:
1. Authenticate with SAP BTP AICore
2. Check/create necessary deployments
3. Initialize the MCP server on the configured port

## 🔧 Configuration Details

### SAP BTP AICore Service Key

Your service key should contain these fields:
```json
{
  "clientid": "your-client-id",
  "clientsecret": "your-client-secret",
  "url": "https://api.ai.ml.hana.ondemand.com",
  "identityzone": "your-subdomain",
  "identityzoneid": "zone-id",
  "appname": "your-app-name",
  "serviceurls": {
    "AI_API_URL": "https://api.ai.ml.hana.ondemand.com"
  }
}
```

### Deployment Options

#### Orchestration Service (Recommended)
The Orchestration service provides a unified interface for multiple AI capabilities:
- Set `SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID`
- Supports both embeddings and chat completions
- Includes built-in content filtering and data masking

#### Direct Services
Alternatively, use direct AI Core services:
- Set `SAP_BTP_AICORE_EMBEDDING_DEPLOYMENT_ID` for embeddings
- Set `SAP_BTP_AICORE_CHAT_DEPLOYMENT_ID` for chat completions

### Model Configuration

Supported embedding models:
- `text-embedding-3-large` (default, 1536 dimensions)
- `text-embedding-3-small` (1536 dimensions)
- `text-embedding-ada-002` (1536 dimensions)

Supported chat models:
- `gpt-4o` (default)
- `gpt-4`
- `gpt-3.5-turbo`

## 🔍 Usage

The server provides the same MCP tools as the original, but now powered by SAP BTP AICore:

### Available Tools

1. **crawl_single_page**: Crawl a single webpage and store in vector database
2. **smart_crawl_url**: Intelligently crawl URLs (sitemaps, text files, or recursive)
3. **get_available_sources**: List all crawled sources
4. **perform_rag_query**: Search and retrieve relevant content
5. **search_code_examples**: Search for code examples (if enabled)
6. **Knowledge Graph Tools** (if enabled):
   - `check_ai_script_hallucinations`
   - `query_knowledge_graph`
   - `parse_github_repository`

### Example Usage

```python
# Using the MCP client
import mcp

client = mcp.Client("mcp-crawl4ai-rag")

# Crawl a website
result = await client.call_tool("smart_crawl_url", {
    "url": "https://docs.example.com",
    "max_depth": 2
})

# Perform RAG query
result = await client.call_tool("perform_rag_query", {
    "query": "How to configure authentication?",
    "match_count": 5
})
```

## 🚨 Troubleshooting

### Authentication Issues

**Error**: `Authentication failed`
- Verify your client ID and secret are correct
- Check that the auth URL matches your identity zone
- Ensure your service key is not expired

### Deployment Issues

**Error**: `No embedding deployment configured`
- Set either `SAP_BTP_AICORE_ORCHESTRATION_DEPLOYMENT_ID` or individual deployment IDs
- Check that deployments are in "RUNNING" status in AI Launchpad
- Verify you have access to the specified resource group

### API Errors

**Error**: `API request failed`
- Check your base URL is correct
- Verify network connectivity to SAP BTP AICore
- Check rate limits and quotas in AI Launchpad

### Token Issues

**Error**: `Token expired` or `401 Unauthorized`
- The client automatically refreshes tokens, but check your service key validity
- Verify the token endpoint URL is correct

## 🔄 Migration from OpenAI

If you're migrating from the original OpenAI-based server:

1. **Environment Variables**: Replace OpenAI variables with SAP BTP AICore equivalents
2. **Dependencies**: No additional Python packages needed
3. **Data**: Existing Supabase data remains compatible
4. **Functionality**: All features work identically

### Key Differences

| Aspect | OpenAI Version | SAP BTP AICore Version |
|--------|----------------|------------------------|
| Authentication | API Key | OAuth2 Client Credentials |
| Embedding API | OpenAI Embeddings | AI Core Embeddings/Orchestration |
| Chat API | OpenAI Chat | AI Core Chat/Orchestration |
| Rate Limiting | OpenAI limits | SAP BTP AICore limits |
| Models | OpenAI models | Azure OpenAI models via AI Core |

## 📊 Performance Considerations

- **Batch Processing**: The client supports batch embedding creation for efficiency
- **Token Caching**: Access tokens are cached and automatically refreshed
- **Retry Logic**: Built-in exponential backoff for transient failures
- **Connection Pooling**: Reuses HTTP connections for better performance

## 🔐 Security

- **Token Security**: Access tokens are stored in memory only
- **TLS**: All communications use HTTPS
- **Credentials**: Service credentials should be stored securely
- **Data Privacy**: Supports SAP Data Privacy Integration when using Orchestration

## 📈 Monitoring

Monitor your usage through:
- **AI Launchpad**: View deployment status and metrics
- **BTP Cockpit**: Monitor service usage and quotas
- **Server Logs**: Check application logs for errors and performance

## 🤝 Support

For issues related to:
- **SAP BTP AICore**: Check SAP Community and official documentation
- **Server Implementation**: Review logs and configuration
- **MCP Protocol**: Refer to MCP documentation

## 📚 Additional Resources

- [SAP BTP AICore Documentation](https://help.sap.com/docs/AI_CORE)
- [AI Launchpad User Guide](https://help.sap.com/docs/AI_LAUNCHPAD)
- [SAP AI SDK Documentation](https://sap.github.io/ai-sdk/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
