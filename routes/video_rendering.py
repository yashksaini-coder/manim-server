from flask import Blueprint, jsonify, current_app, request, Response
import subprocess
import os
import re
import json
import sys
import traceback
import shutil
from typing import Union
import uuid
import time
import requests
import boto3
from dotenv import load_dotenv
from service import cache, queue, redis_conn
from rq.job import Job

# Import helpers from video_worker
from routes.video_worker import render_video_task

load_dotenv()

video_rendering_bp = Blueprint("video_rendering", __name__)

# Configuration
USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE") or False
BASE_URL = os.getenv("BASE_URL")
DO_SPACES_ACCESS_KEY = os.getenv("DO_SPACES_ACCESS_KEY")
DO_SPACES_ACCESS_SECRET = os.getenv("DO_SPACES_ACCESS_SECRET")
DO_SPACES_REGION = os.getenv("DO_SPACES_REGION")
DO_SPACES_BUCKET = os.getenv("DO_SPACES_BUCKET")
DO_SPACES_ENDPOINT = os.getenv("DO_SPACES_ENDPOINT")


def upload_to_digital_ocean_storage(file_path: str, video_storage_file_name: str) -> str:
    """
    Uploads the video to DigitalOcean Spaces and returns the public URL.
    """
    client = boto3.client(
        's3',
        region_name=DO_SPACES_REGION,
        endpoint_url=DO_SPACES_ENDPOINT,
        aws_access_key_id=DO_SPACES_ACCESS_KEY,
        aws_secret_access_key=DO_SPACES_ACCESS_SECRET
    )

    # Ensure the file name has .mp4 extension
    if not video_storage_file_name.endswith('.mp4'):
        video_storage_file_name += '.mp4'

    client.upload_file(
        file_path,
        DO_SPACES_BUCKET,
        video_storage_file_name,
        ExtraArgs={'ACL': 'public-read', 'ContentType': 'video/mp4'}
    )

    return f"{DO_SPACES_ENDPOINT}/{DO_SPACES_BUCKET}/{video_storage_file_name}"


def move_to_public_folder(
    file_path: str, video_storage_file_name: str, base_url: Union[str, None] = None
) -> str:
    """
    Moves the video to the public folder and returns the URL.
    """
    public_folder = os.path.join(os.path.dirname(__file__), "public")
    os.makedirs(public_folder, exist_ok=True)

    new_file_name = f"{video_storage_file_name}.mp4"
    new_file_path = os.path.join(public_folder, new_file_name)

    shutil.move(file_path, new_file_path)

    # Use the provided base_url if available, otherwise fall back to BASE_URL
    url_base = base_url if base_url else BASE_URL
    video_url = f"{url_base.rstrip('/')}/public/{new_file_name}"
    return video_url


def get_frame_config(aspect_ratio):
    if aspect_ratio == "16:9":
        return (3840, 2160), 14.22
    elif aspect_ratio == "9:16":
        return (1080, 1920), 8.0
    elif aspect_ratio == "1:1":
        return (1080, 1080), 8.0
    else:
        return (3840, 2160), 14.22

@video_rendering_bp.route("/v1/render/video", methods=["POST"])
def render_video_route():
    """
    Endpoint to render a video using Manim based on user-provided code and parameters.
    """
    code = request.json.get("code")
    file_name = request.json.get("file_name")
    file_class = request.json.get("file_class")
    user_id = request.json.get("user_id") or str(uuid.uuid4())
    project_name = request.json.get("project_name")
    iteration = request.json.get("iteration")
    aspect_ratio = request.json.get("aspect_ratio")
    stream = request.json.get("stream", False)
    video_storage_file_name = f"video-{user_id}-{project_name}-{iteration}"
    if not code:
        return jsonify(error="No code provided"), 400
    args = {
        'code': code,
        'file_name': file_name,
        'file_class': file_class,
        'user_id': user_id,
        'project_name': project_name,
        'iteration': iteration,
        'aspect_ratio': aspect_ratio,
        'video_storage_file_name': video_storage_file_name,
        'stream': stream
    }
    
    # Enqueue the render_video_task function from video_worker
    job = queue.enqueue(render_video_task, args)
    return jsonify({"job_id": job.get_id()}), 202


@video_rendering_bp.route("/v1/render/video/status/<job_id>", methods=["GET"])
def get_video_status(job_id):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception as e:
        return jsonify({"status": "not_found", "error": str(e)}), 404
    if job.is_finished:
        return jsonify({"status": "finished", "result": job.result})
    elif job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})
    else:
        return jsonify({"status": "in_progress"})

