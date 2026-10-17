"""
Metrics instrumentation.

Provides Prometheus metrics for tracking request counts, durations, token usage,
and analysis scores. Gracefully falls back to no-ops if prometheus_client is missing.
"""
from __future__ import annotations

from typing import Any

from fastapi import Response

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    
    class NoOpMetric:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def labels(self, *args: Any, **kwargs: Any) -> Any:
            return self
        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass
        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass
            
    Counter = NoOpMetric # type: ignore
    Histogram = NoOpMetric # type: ignore


if HAS_PROMETHEUS:
    REQUEST_COUNT = Counter(
        'truvix_ai_requests_total',
        'Total number of requests',
        ['endpoint', 'method', 'status']
    )
    REQUEST_DURATION = Histogram(
        'truvix_ai_request_duration_seconds',
        'Request duration in seconds',
        ['endpoint']
    )
    AI_TOKENS_USED = Counter(
        'truvix_ai_tokens_total',
        'Total number of AI tokens used',
        ['direction']
    )
    ANALYSIS_SCORE = Histogram(
        'truvix_ai_analysis_score',
        'Distribution of analysis trust scores',
        buckets=[0, 20, 40, 60, 80, 100]
    )
else:
    REQUEST_COUNT = Counter('truvix_ai_requests_total', 'Total number of requests', ['endpoint', 'method', 'status'])
    REQUEST_DURATION = Histogram('truvix_ai_request_duration_seconds', 'Request duration', ['endpoint'])
    AI_TOKENS_USED = Counter('truvix_ai_tokens_total', 'Total tokens', ['direction'])
    ANALYSIS_SCORE = Histogram('truvix_ai_analysis_score', 'Score distribution', buckets=[0, 20, 40, 60, 80, 100])


def metrics_endpoint() -> Response:
    """Returns the current metrics in Prometheus text format."""
    if not HAS_PROMETHEUS:
        return Response(content="Metrics not available (prometheus_client missing)", status_code=404)
        
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
