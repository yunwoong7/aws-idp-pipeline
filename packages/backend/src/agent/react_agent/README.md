# ReAct Agent - Enhanced Version

## Overview

This is an enhanced version of the ReAct Agent system built on LangGraph with comprehensive improvements in reliability, performance, and maintainability.

## Key Improvements

### 🚀 Performance & Memory Management
- **Thread-safe conversation management** with LRU cache and size limits
- **Memory leak prevention** through automatic cleanup of old threads and messages
- **Configurable limits** for threads and messages per thread
- **Automatic summarization** to manage long conversations

### 🛡️ Error Handling & Recovery
- **Structured error classification** with specific error types
- **Automatic recovery strategies** for common failures (MCP disconnection, timeouts, rate limits)
- **Graceful degradation** when external services are unavailable
- **Enhanced retry logic** with exponential backoff

### ⚙️ Configuration Management
- **Centralized configuration** with environment variable support
- **Runtime configuration updates** without restart
- **Validation and type checking** for all configuration values
- **Hot-reload capability** for configuration changes

### 📊 Monitoring & Observability
- **Structured logging** with JSON format and contextual information
- **Comprehensive metrics collection** (conversations, messages, errors, performance)
- **Performance tracking** with execution time measurements
- **Health monitoring** with detailed statistics

### 🔒 Security & Validation
- **Input validation** for thread IDs and message content
- **Content sanitization** to remove sensitive information
- **Size limits** for attachments and messages
- **Thread-safe operations** throughout the system

## Architecture

```
ReactAgent (Main)
├── ConversationManager (Thread-safe history management)
├── GraphBuilder (LangGraph workflow)
├── ErrorHandler (Error classification & recovery)
├── ConfigManager (Centralized configuration)
├── MetricsCollector (Performance monitoring)
├── AgentLogger (Structured logging)
└── Utils (Enhanced utilities)
```

## Configuration

Configuration can be set via environment variables with the `AGENT_` prefix:

```bash
# Model Configuration
AGENT_MODEL_ID=claude-3-sonnet-20240229
AGENT_MAX_TOKENS=4096
AGENT_MODEL_TIMEOUT=60.0
AGENT_MAX_RETRIES=3

# Memory Management
AGENT_SUMMARIZATION_THRESHOLD=12
AGENT_MAX_CONVERSATION_MESSAGES=10
AGENT_MAX_THREADS=100
AGENT_MAX_MESSAGES_PER_THREAD=50

# MCP Configuration
AGENT_MCP_JSON_PATH=/path/to/mcp/config.json
AGENT_MCP_CONNECTION_TIMEOUT=30.0
AGENT_MCP_RETRY_ATTEMPTS=3

# Monitoring
AGENT_DEBUG_MODE=false
AGENT_LOG_LEVEL=INFO
AGENT_ENABLE_METRICS=true
AGENT_METRICS_RETENTION_HOURS=24

# Security
AGENT_MAX_ATTACHMENT_SIZE_MB=50
AGENT_MAX_ATTACHMENTS_PER_REQUEST=10
AGENT_ENABLE_CONTENT_FILTERING=true
```

## Usage

### Basic Usage

```python
from agent import ReactAgent

# Initialize with configuration
agent = ReactAgent(
    model_id="claude-3-sonnet-20240229",
    max_tokens=4096,
    mcp_json_path="/path/to/mcp/config.json"
)

# Start the agent
await agent.startup()

# Stream responses
async for message, metadata in agent.astream(
    input_state=InputState(messages=[HumanMessage(content="Hello!")]),
    config={"configurable": {"thread_id": "user123"}},
    files=[]  # Optional file attachments
):
    print(f"Response: {message.content}")

# Cleanup
await agent.shutdown()
```

### Advanced Usage with Metrics

```python
from agent.metrics import get_metrics
from agent.config import config_manager

# Get metrics
metrics = get_metrics()
stats = metrics.get_metrics_summary()
print(f"Total conversations: {stats['total_conversations']}")
print(f"Average response time: {stats['averages']['response_time_seconds']}s")

# Update configuration at runtime
config_manager.update_config({
    "max_threads": 200,
    "debug_mode": True
})

# Get memory statistics
memory_stats = agent.convo_manager.get_memory_stats()
print(f"Memory usage: {memory_stats['memory_usage_percent']}%")
```

## Error Recovery

The system automatically handles common error scenarios:

1. **MCP Connection Failures**: Gracefully degrades to basic functionality
2. **Model Timeouts**: Implements exponential backoff retry
3. **Rate Limiting**: Informs user and suggests retry later
4. **Memory Issues**: Automatically cleans up old data

## Monitoring

### Logs

Logs are structured in JSON format and written to:
- `logs/agent.log` - All logs
- `logs/errors.log` - Error logs only
- `logs/performance.log` - Performance metrics

### Metrics

Key metrics tracked:
- Conversation duration and message count
- Tool execution success rates and timing
- Model API call performance
- Error rates by type
- Memory usage patterns

### Health Checks

```python
# Get health status
health = agent.get_health_status()
print(f"MCP healthy: {health['healthy']}")
print(f"Tools available: {health['tools_count']}")

# Get conversation statistics
stats = agent.get_conversation_stats()
print(f"Active threads: {stats['active_threads']}")
print(f"Total messages: {stats['total_messages']}")
```

## Migration Guide

### From Previous Version

1. **Update imports**: Some utilities moved to submodules
2. **Configuration**: Use environment variables instead of hardcoded values
3. **Error handling**: Automatic error recovery is now built-in
4. **Memory management**: Old conversation cleanup is automatic

### Breaking Changes

- `ConversationManager` constructor now requires memory limits
- Some utility functions moved to class methods
- Error handling is now automatic (no need for manual try/catch)

## Performance Optimizations

1. **Memory-efficient conversation storage** with automatic cleanup
2. **Thread-safe operations** prevent race conditions
3. **Configurable timeouts** prevent hanging operations
4. **Efficient retry logic** with exponential backoff
5. **Lazy loading** of expensive resources

## Best Practices

1. **Set appropriate memory limits** based on your usage patterns
2. **Monitor metrics regularly** to identify performance issues
3. **Use structured logging** for better debugging
4. **Configure timeouts** based on your latency requirements
5. **Enable content filtering** for security in production

## Troubleshooting

### High Memory Usage
- Reduce `max_threads` or `max_messages_per_thread`
- Lower `summarization_threshold` for more frequent cleanup
- Check metrics for memory usage patterns

### Slow Response Times
- Increase `model_timeout` if needed
- Check MCP tool performance in logs
- Monitor network connectivity to external services

### Frequent Errors
- Review error statistics in metrics
- Check MCP service health
- Verify configuration values

### Configuration Issues
- Use `config.validate_configuration()` to check settings
- Review environment variable names and values
- Check file paths and permissions

## Contributing

When contributing improvements:

1. Add appropriate tests for new functionality
2. Update configuration schema if adding new settings
3. Include metrics for performance-critical features
4. Document breaking changes and migration steps
5. Follow the structured logging patterns

## License

[Your license here]