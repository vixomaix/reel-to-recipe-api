"""
OpenTelemetry Tracing Configuration
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor


def setup_tracing(service_name: str = "reel-to-recipe-api"):
    """Setup distributed tracing with OpenTelemetry"""
    
    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "2.0.0"
    })
    
    # Create provider
    provider = TracerProvider(resource=resource)
    
    # Add exporter if OTLP endpoint configured
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    
    # Set global provider
    trace.set_tracer_provider(provider)
    
    # Instrument libraries
    RedisInstrumentor().instrument()
    AsyncPGInstrumentor().instrument()
    
    return provider


def get_tracer(name: str = "reel-to-recipe-api"):
    """Get tracer instance"""
    return trace.get_tracer(name)


def instrument_fastapi(app):
    """Instrument FastAPI app"""
    FastAPIInstrumentor.instrument_app(app)
