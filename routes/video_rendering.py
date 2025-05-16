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
async def render_video_route(request: Request, body: RenderRequest):
    code = body.code
    file_name = body.file_name
    file_class = body.file_class
    user_id = body.user_id or str(uuid.uuid4())
    project_name = body.project_name
    iteration = body.iteration
    aspect_ratio = body.aspect_ratio
    stream = body.stream
    video_storage_file_name = f"video-{user_id}-{project_name}-{iteration}"
    if not code:
        return JSONResponse(content={"error": "No code provided"}, status_code=400)
    frame_size, frame_width = get_frame_config(aspect_ratio)
    modified_code = f"""
from manim import *
from math import *
config.frame_size = {frame_size}
config.frame_width = {frame_width}

{code}
    """
    temp_file_name = f"scene_{os.urandom(2).hex()}.py"
    api_dir = os.path.dirname(os.path.dirname(__file__))
    public_dir = os.path.join(api_dir, "public")
    os.makedirs(public_dir, exist_ok=True)
    file_path = os.path.join(public_dir, temp_file_name)
    with open(file_path, "w") as f:
        f.write(modified_code)
    def render_video():
        process = None
        video_file_path = None
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
            current_animation = -1
            current_percentage = 0
            error_output = []
            in_error = False
            while True:
                output = process.stdout.readline()
                error = process.stderr.readline()
                if output == "" and error == "" and process.poll() is not None:
                    break
                if output:
                    print("STDOUT:", output.strip())
                if error:
                    print("STDERR:", error.strip())
                    error_output.append(error.strip())
                if "is not in the script" in error:
                    in_error = True
                    continue
                if "Traceback (most recent call last)" in error:
                    in_error = True
                    continue
                if in_error:
                    if error.strip() == "":
                        in_error = False
                        full_error = "\n".join(error_output)
                        yield f'{{"error": {json.dumps(full_error)}}}\n'
                        return
                    continue
                animation_match = re.search(r"Animation (\d+):", error)
                if animation_match:
                    new_animation = int(animation_match.group(1))
                    if new_animation != current_animation:
                        current_animation = new_animation
                        current_percentage = 0
                        yield f'{{"animationIndex": {current_animation}, "percentage": 0}}\n'
                percentage_match = re.search(r"(\d+)%", error)
                if percentage_match:
                    new_percentage = int(percentage_match.group(1))
                    if new_percentage != current_percentage:
                        current_percentage = new_percentage
                        yield f'{{"animationIndex": {current_animation}, "percentage": {current_percentage}}}\n'
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
                    print(f"Video file not found. Files in current directory: {os.listdir(os.path.dirname(video_file_path))}")
                    raise FileNotFoundError(f"Video file not found at {video_file_path}")
                print(f"Files in video file directory: {os.listdir(os.path.dirname(video_file_path))}")
                video_url = upload_to_digital_ocean_storage(
                    video_file_path, video_storage_file_name
                )
                print(f"Video URL: {video_url}")
                if stream:
                    yield f'{{ "video_url": "{video_url}" }}\n'
                    sys.stdout.flush()
                else:
                    yield json.dumps({
                        "message": "Video generation completed",
                        "video_url": video_url,
                    })
            else:
                full_error = "\n".join(error_output)
                yield f'{{"error": {json.dumps(full_error)}}}\n'
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            traceback.print_exc()
            print(f"Files in current directory after error: {os.listdir('.')}")
            yield f'{{"error": "Unexpected error occurred: {str(e)}"}}\n'
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed temporary file: {file_path}")
                if video_file_path and os.path.exists(video_file_path):
                    os.remove(video_file_path)
                    print(f"Removed temporary video file: {video_file_path}")
            except Exception as e:
                print(f"Error removing temporary file {file_path}: {e}")
    def process_render_results():
        video_url = None
        error = None
        try:
            for result in render_video():
                print(f"Generated result: {result}")
                # Always try to parse as JSON
                if isinstance(result, str):
                    try:
                        result_json = json.loads(result)
                        if "video_url" in result_json:
                            video_url = result_json["video_url"]
                        if "error" in result_json:
                            error = result_json["error"]
                            break
                    except Exception:
                        # If not JSON, skip
                        pass
            if error:
                return {"error": error}, 500
            if video_url:
                return {
                    "message": "Video generation completed",
                    "video_url": video_url,
                }, 200
            else:
                return {
                    "message": "Video generation completed, but no URL was found"
                }, 200
        except StopIteration:
            if video_url:
                return {
                    "message": "Video generation completed",
                    "video_url": video_url,
                }, 200
            else:
                return {
                    "message": "Video generation completed, but no URL was found"
                }, 200
        except Exception as e:
            print(f"Error in processing render results: {e}")
            traceback.print_exc()
            return {"error": str(e)}, 500
    if stream:
        return StreamingResponse(
            render_video(), media_type="text/event-stream", status_code=207
        )
    else:
        def generate():
            future = executor.submit(process_render_results)
            response_data, status_code = future.result()
            yield json.dumps(response_data)
        return StreamingResponse(
            generate(),
            media_type="application/json",
            status_code=200
        )

