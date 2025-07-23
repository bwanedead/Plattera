"""
Main FastAPI Application
=======================

Entry point for the Plattera backend API server.
"""

import uvicorn
import logging
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from api.router import api_router
from utils.health_monitor import get_health_monitor

# Custom colored formatter for better log readability
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and emojis for better log readability"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    def format(self, record):
        # Add emoji and color to log level
        emoji = self.EMOJIS.get(record.levelname, '')
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Format the message
        record.levelname = f"{color}{emoji} {record.levelname}{reset}"
        return super().format(record)

# Set up the custom logger
def setup_logging():
    """Set up enhanced logging with visual indicators"""
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    
    # Configure root logger
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Silence noisy libraries
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.WARNING)
    
    # Reduce alignment engine debug spam - these are the main culprits
    logging.getLogger('pipelines.image_to_text.json_alignment').setLevel(logging.WARNING)
    logging.getLogger('pipelines.image_to_text.alignment_engines').setLevel(logging.INFO)
    logging.getLogger('pipelines.image_to_text.alignment_engines.semantic_engine').setLevel(logging.WARNING)
    logging.getLogger('pipelines.image_to_text.alignment_engines.contextual_engine').setLevel(logging.WARNING)
    logging.getLogger('pipelines.image_to_text.alignment_engines.comparison_engine').setLevel(logging.WARNING)
    
    # Force apply the custom formatter to all existing loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger_obj = logging.getLogger(logger_name)
        logger_obj.handlers = []  # Clear handlers
        logger_obj.addHandler(console_handler)  # Add our custom handler

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Plattera API",
    description="Legal document processing and alignment API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)

# Global health monitor instance
health_monitor = None

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global health_monitor
    logger.info("🚀 Starting Plattera API Server")
    
    # Initialize health monitor
    health_monitor = get_health_monitor()
    logger.info("🏥 Health monitoring initialized")
    
    # Perform initial health check
    health_status = health_monitor.check_system_health()
    logger.info(f"🏥 Initial health check: {health_status['overall_status']}")
    
    logger.info("✅ Plattera API Server started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    global health_monitor
    logger.info("🛑 Shutting down Plattera API Server")
    
    try:
        # Perform final cleanup
        if health_monitor:
            logger.info("🧹 Performing final cleanup...")
            cleanup_results = health_monitor.perform_cleanup(force=True)
            if cleanup_results['status'] == 'completed':
                logger.info("✅ Final cleanup completed successfully")
            else:
                logger.warning(f"⚠️ Final cleanup issues: {cleanup_results.get('errors', [])}")
        
        # Force garbage collection
        import gc
        collected = gc.collect()
        logger.info(f"🧹 Final garbage collection: freed {collected} objects")
        
        logger.info("✅ Plattera API Server shutdown complete")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with cleanup"""
    logger.error(f"❌ Unhandled exception: {exc}")
    
    # Perform emergency cleanup on unhandled exceptions
    try:
        if health_monitor:
            health_monitor.perform_cleanup(force=True)
    except Exception as cleanup_error:
        logger.error(f"❌ Emergency cleanup failed: {cleanup_error}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if app.debug else "An unexpected error occurred"
        }
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Plattera API v2.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    logger.info("🔧 Starting Plattera API Server in development mode")
    
    # Configure uvicorn settings
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    ) 