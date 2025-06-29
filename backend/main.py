"""
Plattera Backend API v2.0
Clean architecture with central API hub
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env file

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.router import api_router
import logging
import sys

# Configure enhanced logging with visual indicators
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and visual indicators"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m',       # Reset
        'BOLD': '\033[1m',        # Bold
    }
    
    def format(self, record):
        # Check if the message contains visual indicators
        visual_indicators = ['🔍', '✅', '🔧', '🧬', '🔥', '⚡', '📊', '🎯', '🔄', '❌', '⚠️', '🏆', '📋', '📄', '🎨', '🚀', '💡']
        has_indicator = any(indicator in record.getMessage() for indicator in visual_indicators)
        
        if has_indicator:
            # For messages with visual indicators, use bold green for level only
            level_color = self.COLORS['BOLD'] + self.COLORS['INFO']
            reset = self.COLORS['RESET']
            formatted = f"{level_color}[{record.levelname}]{reset} {record.getMessage()}"
        else:
            # For regular messages, use normal formatting
            formatted = f"[{record.levelname}] {record.getMessage()}"
        
        return formatted

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

# Create FastAPI application
app = FastAPI(
    title="Plattera API",
    description="Legal document processing with modular LLM and OCR services",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the central API router
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Plattera API v2.0...")
    
    # Import here to trigger service discovery
    from services.registry import get_registry
    registry = get_registry()
    
    logger.info("🔍 Discovering services...")
    
    # Get detailed service information
    llm_services = registry.get_llm_services()
    ocr_services = registry.get_ocr_services()
    service_info = registry.get_service_info()
    
    # Log LLM services with detailed model info
    for name, service in llm_services.items():
        models = service.get_models()
        logger.info(f"✅ LLM: {name} ({len(models)} models)")
        for model_id in models.keys():
            logger.info(f"    🤖 {model_id}")
    
    # Log OCR services with detailed model info
    for name, service in ocr_services.items():
        models = service.get_models()
        logger.info(f"✅ OCR: {name} ({len(models)} models)")
        for model_id in models.keys():
            logger.info(f"    🤖 {model_id}")
    
    logger.info(f"✅ Loaded {len(llm_services)} LLM services, {len(ocr_services)} OCR services")
    logger.info(f"📊 Total models available: {service_info['total_models']}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Plattera API v2.0 - Legal Document Processing",
        "status": "running",
        "documentation": "/docs",
        "api_root": "/api"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Plattera API v2.0...")
    uvicorn.run(app, host="0.0.0.0", port=8000) 