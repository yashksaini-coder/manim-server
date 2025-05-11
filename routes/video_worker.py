import subprocess
import os
import sys
import traceback
from typing import Union
import uuid
import time
import requests
from dotenv import load_dotenv

# Import shared utility functions
from routes.video_utils import (
    get_frame_config,
    move_to_public_folder,
    upload_to_digital_ocean_storage,
    USE_LOCAL_STORAGE,
    BASE_URL
)

# Load environment variables
load_dotenv()


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