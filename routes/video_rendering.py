from flask import Blueprint, jsonify, request
import os
import uuid
from service import queue, redis_conn
from rq.job import Job
from dotenv import load_dotenv

# Import shared utility functions instead of defining them here
from routes.video_utils import get_frame_config

load_dotenv()

video_rendering_bp = Blueprint("video_rendering", __name__)

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
    
    # Use the exact module path as a string
    job = queue.enqueue('routes.video_worker.render_video_task', args)
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

