import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.templating import Jinja2Templates

# Load environment variables from .env file
load_dotenv()

# Import routers from routes
def get_router(module):
    # Helper to get the 'router' object from a module
    return getattr(module, 'router')

from routes import video_rendering, code_generation

# Initialize FastAPI app
app = FastAPI()

# Enable CORS for all routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/public", StaticFiles(directory="public"), name="public")

# Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def hello_world(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Register all routers (endpoints)
app.include_router(get_router(video_rendering))
app.include_router(get_router(code_generation))

# To run: uvicorn app:app --host 0.0.0.0 --port 8000
