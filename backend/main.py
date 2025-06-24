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

# Configure logging
logging.basicConfig(level=logging.INFO)
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