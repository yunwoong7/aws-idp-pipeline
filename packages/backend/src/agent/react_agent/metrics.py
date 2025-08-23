"""
Metrics collection and monitoring for ReAct Agent
"""
import time
import threading
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from .config import config_manager


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConversationMetrics:
    """Metrics for a conversation"""
    thread_id: str
    start_time: float
    end_time: Optional[float] = None
    message_count: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    error_count: int = 0
    model_call_duration: float = 0.0
    tool_execution_duration: float = 0.0


class MetricsCollector:
    """Thread-safe metrics collector"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._conversation_metrics: Dict[str, ConversationMetrics] = {}
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._start_time = time.time()
    
    def increment_counter(self, name: str, value: int = 1, labels: Dict[str, str] = None) -> None:
        """Increment a counter metric"""
        with self._lock:
            metric_key = f"{name}:{self._labels_to_string(labels)}"
            self._counters[metric_key] += value
            self._add_metric_point(name, value, labels)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Set a gauge metric"""
        with self._lock:
            metric_key = f"{name}:{self._labels_to_string(labels)}"
            self._gauges[metric_key] = value
            self._add_metric_point(name, value, labels)
    
    def record_histogram(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Record a histogram value"""
        with self._lock:
            metric_key = f"{name}:{self._labels_to_string(labels)}"
            self._histograms[metric_key].append(value)
            # Keep only recent values
            if len(self._histograms[metric_key]) > 1000:
                self._histograms[metric_key] = self._histograms[metric_key][-1000:]
            self._add_metric_point(name, value, labels)
    
    def start_conversation(self, thread_id: str) -> None:
        """Start tracking a conversation"""
        with self._lock:
            self._conversation_metrics[thread_id] = ConversationMetrics(
                thread_id=thread_id,
                start_time=time.time()
            )
            self.increment_counter("conversations_started")
    
    def end_conversation(self, thread_id: str) -> None:
        """End tracking a conversation"""
        with self._lock:
            if thread_id in self._conversation_metrics:
                conversation = self._conversation_metrics[thread_id]
                conversation.end_time = time.time()
                
                # Record conversation duration
                duration = conversation.end_time - conversation.start_time
                self.record_histogram("conversation_duration", duration)
                
                # Record final metrics
                self.increment_counter("conversations_completed")
                self.record_histogram("messages_per_conversation", conversation.message_count)
                self.record_histogram("tools_per_conversation", conversation.tool_calls)
                self.record_histogram("tokens_per_conversation", conversation.total_tokens)
    
    def record_message(self, thread_id: str, message_type: str, token_count: int = 0) -> None:
        """Record a message in a conversation"""
        with self._lock:
            if thread_id in self._conversation_metrics:
                self._conversation_metrics[thread_id].message_count += 1
                self._conversation_metrics[thread_id].total_tokens += token_count
            
            self.increment_counter("messages_total", labels={"type": message_type})
            if token_count > 0:
                self.record_histogram("message_tokens", token_count, labels={"type": message_type})
    
    def record_tool_call(self, thread_id: str, tool_name: str, duration: float, success: bool) -> None:
        """Record a tool call"""
        with self._lock:
            if thread_id in self._conversation_metrics:
                self._conversation_metrics[thread_id].tool_calls += 1
                self._conversation_metrics[thread_id].tool_execution_duration += duration
                if not success:
                    self._conversation_metrics[thread_id].error_count += 1
            
            status = "success" if success else "error"
            self.increment_counter("tool_calls_total", labels={"tool": tool_name, "status": status})
            self.record_histogram("tool_duration", duration, labels={"tool": tool_name})
    
    def record_model_call(self, thread_id: str, duration: float, token_count: int, success: bool) -> None:
        """Record a model API call"""
        with self._lock:
            if thread_id in self._conversation_metrics:
                self._conversation_metrics[thread_id].model_call_duration += duration
                if not success:
                    self._conversation_metrics[thread_id].error_count += 1
            
            status = "success" if success else "error"
            self.increment_counter("model_calls_total", labels={"status": status})
            self.record_histogram("model_call_duration", duration)
            if token_count > 0:
                self.record_histogram("model_call_tokens", token_count)
    
    def record_error(self, error_type: str, context: Dict[str, str] = None) -> None:
        """Record an error"""
        labels = {"type": error_type}
        if context:
            labels.update(context)
        self.increment_counter("errors_total", labels=labels)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics"""
        with self._lock:
            current_time = time.time()
            uptime = current_time - self._start_time
            
            # Calculate rates (per minute)
            conversation_rate = self._counters.get("conversations_started:") * 60 / uptime if uptime > 0 else 0
            message_rate = sum(v for k, v in self._counters.items() if k.startswith("messages_total:")) * 60 / uptime if uptime > 0 else 0
            error_rate = sum(v for k, v in self._counters.items() if k.startswith("errors_total:")) * 60 / uptime if uptime > 0 else 0
            
            # Active conversations
            active_conversations = len([c for c in self._conversation_metrics.values() if c.end_time is None])
            
            # Average response time
            model_durations = self._histograms.get("model_call_duration:", [])
            avg_response_time = sum(model_durations) / len(model_durations) if model_durations else 0
            
            # Tool usage statistics
            tool_calls = sum(v for k, v in self._counters.items() if k.startswith("tool_calls_total:"))
            
            return {
                "uptime_seconds": uptime,
                "active_conversations": active_conversations,
                "total_conversations": self._counters.get("conversations_started:", 0),
                "total_messages": sum(v for k, v in self._counters.items() if k.startswith("messages_total:")),
                "total_tool_calls": tool_calls,
                "total_errors": sum(v for k, v in self._counters.items() if k.startswith("errors_total:")),
                "rates_per_minute": {
                    "conversations": round(conversation_rate, 2),
                    "messages": round(message_rate, 2),
                    "errors": round(error_rate, 2)
                },
                "averages": {
                    "response_time_seconds": round(avg_response_time, 3),
                    "messages_per_conversation": self._calculate_average("messages_per_conversation"),
                    "tools_per_conversation": self._calculate_average("tools_per_conversation")
                }
            }
    
    def get_conversation_metrics(self, thread_id: str) -> Optional[ConversationMetrics]:
        """Get metrics for a specific conversation"""
        with self._lock:
            return self._conversation_metrics.get(thread_id)
    
    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most common errors"""
        with self._lock:
            error_counts = [(k.replace("errors_total:", ""), v) for k, v in self._counters.items() if k.startswith("errors_total:")]
            error_counts.sort(key=lambda x: x[1], reverse=True)
            
            return [{"error": error, "count": count} for error, count in error_counts[:limit]]
    
    def cleanup_old_data(self) -> None:
        """Clean up old metric data"""
        config = config_manager.config
        cutoff_time = time.time() - (config.metrics_retention_hours * 3600)
        
        with self._lock:
            # Clean up old conversation metrics
            to_remove = []
            for thread_id, metrics in self._conversation_metrics.items():
                if metrics.end_time and metrics.end_time < cutoff_time:
                    to_remove.append(thread_id)
            
            for thread_id in to_remove:
                del self._conversation_metrics[thread_id]
            
            # Clean up old metric points
            for name, points in self._metrics.items():
                while points and points[0].timestamp < cutoff_time:
                    points.popleft()
    
    def _add_metric_point(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Add a metric point (internal method)"""
        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            labels=labels or {}
        )
        self._metrics[name].append(point)
    
    def _labels_to_string(self, labels: Dict[str, str] = None) -> str:
        """Convert labels to string for key generation"""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def _calculate_average(self, metric_name: str) -> float:
        """Calculate average for a histogram metric"""
        values = self._histograms.get(f"{metric_name}:", [])
        return sum(values) / len(values) if values else 0


# Global metrics collector
metrics_collector = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector"""
    return metrics_collector


class MetricsContext:
    """Context manager for measuring operation duration"""
    
    def __init__(self, metric_name: str, labels: Dict[str, str] = None):
        self.metric_name = metric_name
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            metrics_collector.record_histogram(self.metric_name, duration, self.labels)


def measure_time(metric_name: str, labels: Dict[str, str] = None):
    """Decorator to measure function execution time"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with MetricsContext(metric_name, labels):
                return func(*args, **kwargs)
        return wrapper
    return decorator