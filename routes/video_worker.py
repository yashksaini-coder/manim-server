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

# Load environment variables
load_dotenv()

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


def render_video_task(args):
    """
    The main task that handles video rendering.
    This function is called by the RQ worker to process the job.
    """
    # Unpack arguments
    code = args.get('code')
    file_name = args.get('file_name')
    file_class = args.get('file_class')
    user_id = args.get('user_id')
    project_name = args.get('project_name')
    iteration = args.get('iteration')
    aspect_ratio = args.get('aspect_ratio')
    video_storage_file_name = args.get('video_storage_file_name')
    stream = args.get('stream', False)

    # Determine frame size and width based on aspect ratio
    frame_size, frame_width = get_frame_config(aspect_ratio)

    # Modify the Manim script to include configuration settings
    modified_code = f"""
from manim import *
from math import *
config.frame_size = {frame_size}
config.frame_width = {frame_width}

{code}
    """

    # Create a unique file name
    temp_file_name = f"scene_{os.urandom(2).hex()}.py"
    api_dir = os.path.dirname(os.path.dirname(__file__))  # Go up one level from routes
    public_dir = os.path.join(api_dir, "public")
    os.makedirs(public_dir, exist_ok=True)
    file_path = os.path.join(public_dir, temp_file_name)

    # Write the code to the file
    with open(file_path, "w") as f:
        f.write(modified_code)

    video_url = None
    error = None
    try:
        command_list = [
            "manim",
            file_path,
            file_class,
            "--format=mp4",
            "--media_dir",
            ".",
            "--custom_folders",
        ]
        process = subprocess.Popen(
            command_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.realpath(__file__)),
            text=True,
            bufsize=1,
        )
        error_output = []
        while True:
            output = process.stdout.readline()
            error_line = process.stderr.readline()
            if output == "" and error_line == "" and process.poll() is not None:
                break
            if error_line:
                error_output.append(error_line.strip())
        if process.returncode == 0:
            video_file_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                f"{file_class or 'GenScene'}.mp4"
            )
            if not os.path.exists(video_file_path):
                video_file_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                    f"{file_class or 'GenScene'}.mp4"
                )
            if not os.path.exists(video_file_path):
                error = f"Video file not found at {video_file_path}"
            else:
                if USE_LOCAL_STORAGE == "true":
                    video_url = move_to_public_folder(
                        video_file_path, video_storage_file_name, BASE_URL
                    )
                else:
                    video_url = upload_to_digital_ocean_storage(
                        video_file_path, video_storage_file_name
                    )
        else:
            error = "\n".join(error_output)
    except Exception as e:
        error = str(e)
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if video_url and os.path.exists(video_url):
                os.remove(video_url)
        except Exception:
            pass
    return {"video_url": video_url, "error": error} 