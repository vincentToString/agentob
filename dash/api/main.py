from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from models import DashboardOverview
from metrics_collector import MetricsCollector
from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global metrics collector
metrics_collector = MetricsCollector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Initializing dashboard service...")
    await metrics_collector.initialize()
    logger.info("Dashboard service ready")

    yield

    logger.info("Shutting down dashboard service...")
    await metrics_collector.close()


app = FastAPI(
    title="PROwl Dashboard API",
    description="Backend API for PROwl monitoring dashboard",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# API ROUTES
# ==========================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "dashboard"
    }


@app.get("/api/overview", response_model=DashboardOverview)
async def get_overview():
    """Get complete dashboard overview"""

    # Collect all metrics in parallel
    services = await metrics_collector.get_service_instances()
    queues = await metrics_collector.get_queue_stats()
    recent_reviews = await metrics_collector.get_recent_reviews(limit=20)
    token_estimates = await metrics_collector.get_token_estimates()
    latency_metrics = await metrics_collector.get_latency_metrics()
    aggregate_stats = await metrics_collector.get_aggregate_stats()

    return DashboardOverview(
        timestamp=datetime.utcnow(),
        services=services,
        queues=queues,
        recent_reviews=recent_reviews,
        token_estimates=token_estimates,
        latency_metrics=latency_metrics,
        **aggregate_stats
    )


@app.get("/api/services")
async def get_services():
    """Get service health status"""
    return await metrics_collector.get_service_instances()


@app.get("/api/queues")
async def get_queues():
    """Get queue statistics"""
    return await metrics_collector.get_queue_stats()


@app.get("/api/reviews/recent")
async def get_recent_reviews(limit: int = 50):
    """Get recent review history"""
    return await metrics_collector.get_recent_reviews(limit=limit)


@app.get("/api/reviews/{review_id}")
async def get_review_details(review_id: str):
    """Get detailed review information"""
    # TODO: Implement when review storage is added
    return {"message": "Not implemented yet", "review_id": review_id}


@app.get("/api/tokens/estimates")
async def get_token_estimates():
    """Get token usage estimates for queued items"""
    return await metrics_collector.get_token_estimates()


@app.get("/api/latency")
async def get_latency_metrics():
    """Get latency percentiles for all services"""
    return await metrics_collector.get_latency_metrics()


@app.get("/api/stats/aggregate")
async def get_aggregate_stats():
    """Get aggregate statistics"""
    return await metrics_collector.get_aggregate_stats()


# ==========================================
# TIME-SERIES DATA (for charts)
# ==========================================

@app.get("/api/charts/reviews-over-time")
async def get_reviews_over_time(hours: int = 24):
    """Get review count time series (for line chart)"""
    # TODO: Implement when we store hourly metrics
    return {
        "labels": ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00"],
        "datasets": [
            {
                "label": "Reviews Completed",
                "data": [5, 12, 8, 15, 20, 18]
            }
        ]
    }


@app.get("/api/charts/latency-over-time")
async def get_latency_over_time(hours: int = 24):
    """Get latency time series (for area chart)"""
    # TODO: Implement when we store latency history
    return {
        "labels": ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00"],
        "datasets": [
            {
                "label": "p50 Latency (ms)",
                "data": [450, 420, 480, 460, 440, 430]
            },
            {
                "label": "p95 Latency (ms)",
                "data": [1200, 1150, 1300, 1250, 1180, 1220]
            }
        ]
    }


@app.get("/api/charts/cost-over-time")
async def get_cost_over_time(days: int = 7):
    """Get daily cost time series (for bar chart)"""
    # TODO: Implement when we track daily costs
    return {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "datasets": [
            {
                "label": "Daily Cost ($)",
                "data": [12.50, 15.30, 18.20, 14.80, 16.90, 8.40, 5.20]
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.SERVICE_HOST,
        port=config.SERVICE_PORT,
        reload=True
    )
