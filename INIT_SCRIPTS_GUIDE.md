# MCP Crawl4AI RAG Server - Init Scripts Guide

## 🚀 Available Init Scripts

The MCP Crawl4AI RAG server comes with multiple startup options:

### 1. Manual Start Script (Recommended)
```bash
cd ~/MCP
./start-mcp-crawl4ai.sh
```

### 2. SysV Init Script
```bash
# Start service
sudo /etc/init.d/mcp-crawl4ai-rag-init start

# Stop service  
sudo /etc/init.d/mcp-crawl4ai-rag-init stop

# Check status
sudo /etc/init.d/mcp-crawl4ai-rag-init status

# Restart service
sudo /etc/init.d/mcp-crawl4ai-rag-init restart
```

### 3. Systemd Service (Advanced)
```bash
# Start service
sudo systemctl start mcp-crawl4ai-rag

# Stop service
sudo systemctl stop mcp-crawl4ai-rag

# Enable auto-start at boot
sudo systemctl enable mcp-crawl4ai-rag

# Check status
sudo systemctl status mcp-crawl4ai-rag

# View logs
sudo journalctl -fu mcp-crawl4ai-rag
```

## 📋 Service Components

### Database Backend
- **PostgreSQL**: Running on port 5433 with pgvector extension
- **PostgREST API**: Available at `http://localhost:3000`
- **Docker Containers**: Managed via docker compose

### MCP Server
- **Server URL**: `http://0.0.0.0:8051`
- **Protocol**: MCP (Model Context Protocol)
- **Features**: RAG capabilities with 157K+ documents

## 🔧 Configuration Files

### Service Files Location
- **Systemd**: `/etc/systemd/system/mcp-crawl4ai-rag.service`
- **SysV Init**: `/etc/init.d/mcp-crawl4ai-rag-init`
- **Manual Scripts**: `~/MCP/start-mcp-crawl4ai.sh`, `~/MCP/stop-mcp-crawl4ai.sh`

### Logs Location
- **Manual Script**: Output to console
- **SysV Init**: `/var/log/mcp-crawl4ai-rag.log`
- **Systemd**: `sudo journalctl -u mcp-crawl4ai-rag`

## 🚨 Troubleshooting

### Common Issues

1. **Permission Issues**
   ```bash
   # Ensure scripts are executable
   chmod +x ~/MCP/start-mcp-crawl4ai.sh
   chmod +x ~/MCP/stop-mcp-crawl4ai.sh
   ```

2. **Docker Not Running**
   ```bash
   # Start Docker service
   sudo systemctl start docker
   ```

3. **Port Conflicts**
   ```bash
   # Check if ports are in use
   sudo netstat -tlnp | grep -E ':(3000|5433|8051)'
   ```

4. **Virtual Environment Issues**
   ```bash
   # Reinstall dependencies
   cd ~/MCP/mcp-crawl4ai-rag
   uv sync
   ```

### Service Status Checks

1. **Check Docker Containers**
   ```bash
   cd ~/MCP/mcp-crawl4ai-rag
   docker compose ps
   ```

2. **Test Database Connection**
   ```bash
   curl http://localhost:3000/crawled_pages?limit=1
   ```

3. **Test MCP Server**
   ```bash
   curl http://localhost:8051/health
   ```

## 📖 Service Management Best Practices

### For Production Use
1. **Use Systemd Service**: More robust, automatic restarts, better logging
2. **Enable Auto-start**: `sudo systemctl enable mcp-crawl4ai-rag`
3. **Monitor Logs**: `sudo journalctl -fu mcp-crawl4ai-rag`

### For Development Use
1. **Use Manual Script**: Easier debugging, direct output
2. **Interactive Mode**: Run `./start-mcp-crawl4ai.sh` in terminal

### For System Integration
1. **Use SysV Init**: Compatible with older systems
2. **Chkconfig Support**: For automatic service management

## 🔒 Security Considerations

- Service runs as user `aitoolset` (non-root)
- Docker socket access required for container management
- Network ports: 3000 (PostgREST), 5433 (PostgreSQL), 8051 (MCP Server)
- Log files may contain sensitive information

## 📞 Support

If you encounter issues:
1. Check the logs using the methods above
2. Verify all dependencies are installed
3. Ensure Docker is running and accessible
4. Confirm ports are not in use by other services

The manual start script (`./start-mcp-crawl4ai.sh`) is the most reliable method and should be used as the primary startup mechanism.
