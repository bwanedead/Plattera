"""
Plattera Backend API v2.0
Clean architecture with central API hub
"""
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