from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import subprocess
import os
import re
import json
import sys
import traceback
import shutil
from typing import Optional
import uuid
import boto3
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import asyncio
import tempfile

load_dotenv()

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)

# Configuration
DO_SPACES_ACCESS_KEY = os.getenv("DO_SPACES_ACCESS_KEY")
DO_SPACES_ACCESS_SECRET = os.getenv("DO_SPACES_ACCESS_SECRET")
DO_SPACES_REGION = os.getenv("DO_SPACES_REGION")
DO_SPACES_BUCKET = os.getenv("DO_SPACES_BUCKET")
DO_SPACES_ENDPOINT = os.getenv("DO_SPACES_ENDPOINT")

def upload_to_digital_ocean_storage(file_path: str, video_storage_file_name: str) -> str:
    client = boto3.client(
        's3',
        region_name=DO_SPACES_REGION,
        endpoint_url=DO_SPACES_ENDPOINT,
        aws_access_key_id=DO_SPACES_ACCESS_KEY,
        aws_secret_access_key=DO_SPACES_ACCESS_SECRET
    )
    if not video_storage_file_name.endswith('.mp4'):
        video_storage_file_name += '.mp4'
    client.upload_file(
        file_path,
        DO_SPACES_BUCKET,
        video_storage_file_name,
        ExtraArgs={'ACL': 'public-read', 'ContentType': 'video/mp4'}
    )
    return f"{DO_SPACES_ENDPOINT}/{DO_SPACES_BUCKET}/{video_storage_file_name}"

def get_frame_config(aspect_ratio):
    if aspect_ratio == "16:9":
        return (3840, 2160), 14.22
    elif aspect_ratio == "9:16":
        return (1080, 1920), 8.0
    elif aspect_ratio == "1:1":
        return (1080, 1080), 8.0
    else:
        return (3840, 2160), 14.22

class RenderRequest(BaseModel):
    code: str
    file_name: Optional[str] = None
    file_class: Optional[str] = None
    user_id: Optional[str] = None
    project_name: Optional[str] = None
    iteration: Optional[str] = None
    aspect_ratio: Optional[str] = None
    stream: Optional[bool] = False

@router.post("/v1/render/video")
async def render_video_route(body: RenderRequest):
    code = body.code
    file_name = body.file_name
    file_class = body.file_class
    user_id = body.user_id or str(uuid.uuid4())
    project_name = body.project_name or "project"
    iteration = body.iteration or "0"
    aspect_ratio = body.aspect_ratio
    stream = body.stream
    video_storage_file_name = f"video-{user_id}-{project_name}-{iteration}"

    if not code or not file_class:
        return JSONResponse(content={"error": "No code or file_class provided"}, status_code=400)

    frame_size, frame_width = get_frame_config(aspect_ratio)
    modified_code = f"""
from manim import *
from math import *
config.frame_size = {frame_size}
config.frame_width = {frame_width}

{code}
    """
    temp_file_name = f"scene_{uuid.uuid4().hex}.py"
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, temp_file_name)
    with open(file_path, "w") as f:
        f.write(modified_code)

    # Run manim asynchronously
    manim_cmd = [
        "manim",
        "-ql",
        file_path,
        file_class,
        "--format=mp4",
        "--media_dir", temp_dir,
        "--custom_folders"
    ]
    proc = await asyncio.create_subprocess_exec(
        *manim_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_message = f"Manim failed:\nSTDERR: {stderr.decode()}\nSTDOUT: {stdout.decode()}"
        print(error_message)
        os.remove(file_path)
        return JSONResponse({"error": error_message}, status_code=400)

    # Find the output video file
    video_file = f"{file_class}.mp4"
    video_path = os.path.join(temp_dir, "media", "videos", "tmp", "480p15", video_file)
    if not os.path.exists(video_path):
        # Try to find the file in temp_dir directly as fallback
        video_path = os.path.join(temp_dir, video_file)
        if not os.path.exists(video_path):
            error_message = f"Video file not found at {video_path}"
            print(error_message)
            os.remove(file_path)
            return JSONResponse({"error": error_message}, status_code=500)

    # Upload to DigitalOcean Spaces
    video_url = upload_to_digital_ocean_storage(video_path, video_storage_file_name)

    # Clean up temp files
    os.remove(file_path)
    os.remove(video_path)

    return JSONResponse(
        content={"video_url": video_url},
        status_code=200
    )

