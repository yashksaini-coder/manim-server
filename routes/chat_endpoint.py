from flask import Blueprint, jsonify, request, Response, stream_with_context
import os
import json
import subprocess
import shutil
import string
import random
import re
import base64
from PIL import Image
import io
import time
import uuid
from openai import OpenAI, APIError
from groq import Groq
from public.manimDocs import manimDocs

chat_generation_bp = Blueprint("chat_generation", __name__)

# Function definitions for OpenAI and Groq function calling
functions = {
    "openai": [
        {
            "name": "get_preview",
            "description": "Get a preview of the video animation before giving it. Use this function always, before giving the final code to the user. And use it to generate frames of the video, so you can see it and improve it over time. Also, before using this function, tell the user you will be generating a preview based on the code they see. Always use spaces to maintain the indentation. Indentation is important, otherwise the code will not work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code to get the preview of. Take account the spaces to maintain the indentation.",
                    },
                    "class_name": {
                        "type": "string",
                        "description": "The name of the class to get the preview of. The name of the class should be the same as the name of the class in the code.",
                    }
                },
                "required": ["code", "class_name"],
            },
            "output": {"type": "string", "description": "Images URLs of the animation that will be inserted in the conversation"},
        }
    ],
    "groq": [
        {
            "name": "get_preview",
            "description": "Get a preview of the video animation before giving it. Use this function always, before giving the final code to the user. And use it to generate frames of the video, so you can see it and improve it over time. Also, before using this function, tell the user you will be generating a preview based on the code they see. Always use spaces to maintain the indentation. Indentation is important, otherwise the code will not work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code to get the preview of. Take account the spaces to maintain the indentation.",
                    },
                    "class_name": {
                        "type": "string",
                        "description": "The name of the class to get the preview of. The name of the class should be the same as the name of the class in the code.",
                    }
                },
                "required": ["code", "class_name"],
            },
            "output": {"type": "string", "description": "Images URLs of the animation that will be inserted in the conversation"},
        }
    ]
}

def count_images_in_conversation(messages):
    """
    Count the total number of images in the conversation.
    Returns a tuple of (total_count, list of image messages indices)
    """
    total_images = 0
    image_message_indices = []
    for i, message in enumerate(messages):
        if message.get("role") == "user" and isinstance(message.get("content"), list):
            image_count = sum(1 for content in message["content"] if isinstance(content, dict) and content.get("type") == "image_url")
            if image_count > 0:
                total_images += image_count
                image_message_indices.append(i)
    return total_images, image_message_indices

def manage_conversation_images(messages, new_images_count, engine):
    """
    Manage the conversation to ensure we don't exceed image limits.
    For OpenAI, we maintain only the last 50 images.
    Returns the maximum number of new images we can add.
    """
    if engine != "openai":
        return len(new_images_count)  # No limit for other engines
    MAX_IMAGES = 50
    current_total, image_indices = count_images_in_conversation(messages)
    while current_total > 0 and current_total + new_images_count > MAX_IMAGES and image_indices:
        oldest_image_idx = image_indices[0]
        removed_message = messages.pop(oldest_image_idx)
        removed_images = sum(1 for content in removed_message["content"] 
                           if isinstance(content, dict) and content.get("type") == "image_url")
        current_total -= removed_images
        image_indices = [idx - 1 for idx in image_indices[1:]]
    return min(MAX_IMAGES - current_total, new_images_count)

@chat_generation_bp.route("/v1/generate/chat", methods=["POST"])
def generate_code_chat():
    """
    This endpoint generates code for animations using OpenAI or Groq.
    It supports both OpenAI and Groq models and returns a stream of content.
    """
    print("Received request for /v1/generate/chat")
    data = request.json
    print(f"Request data: {json.dumps(data, indent=2)}")
    messages = data.get("messages", [])
    prompt = data.get("prompt")
    global_prompt = data.get("globalPrompt", "")
    user_id = data.get("userId") or f"user-{uuid.uuid4()}"
    scenes = data.get("scenes", [])
    project_title = data.get("projectTitle", "")
    engine = data.get("engine", "openai")
    model = data.get("model", None)
    selected_scenes = data.get("selectedScenes", [])
    is_for_platform = data.get("isForPlatform", False)
    ENGINE_DEFAULTS = {
      "openai": "gpt-4o",
      "groq": "gemma-7b-it",
      "deepseek": "r1"
    }
    if engine not in ENGINE_DEFAULTS:
        return jsonify({"error": f"Invalid engine. Must be one of: {', '.join(ENGINE_DEFAULTS.keys())}"}), 400
    if not model:
        model = ENGINE_DEFAULTS[engine]
    VALID_MODELS = {
      "openai": ["gpt-4o", "o1-mini"],
      "groq": ["llama-3-70b-8192", "llama-3-8b-8192", "mixtral-8x7b-32768", "gemma-7b-it"],
      "deepseek": ["r1"]
    }
    if model not in VALID_MODELS[engine]:
        return jsonify({
            "error": f"Invalid model '{model}' for engine '{engine}'. Valid models are: {', '.join(VALID_MODELS[engine])}"
        }), 400
    if not messages and prompt:
        messages = [{"role": "user", "content": prompt}]
    general_system_prompt = f"""You are an assistant that creates animations with Manim. Manim is a mathematical animation engine that is used to create videos programmatically. You are running on Animo (www.animo.video), a tool to create videos with Manim.\n\n# What the user can do?\n\nThe user can create a new project, add scenes, and generate the video. You can help the user to generate the video by creating the code for the scenes. The user can add custom rules for you, can select a different aspect ratio, and can change the model (the models are: OpenAI GPT-4o, and Groq llama-3-70b-8192).\n\n# Project\n\nA project can be composed of multiple scenes. This current project (where the user is working on right now) is called '{project_title}', and the following scenes are part of this project. The purpose of showing the list of scenes is to keep the context of the whole video project.\n\n## List of scenes:\n{scenes}\n\n# Behavior Context\n...\n# Manim Library\n{manimDocs}\n"""
    messages.insert(0, {"role": "system", "content": general_system_prompt})
    if engine == "openai":
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        def get_preview(code: str, class_name: str):
            """
            get_preview is a function that generates PNGs frames from a Manim script animation.
            """
            print("Generating preview")
            current_dir = os.path.dirname(os.path.abspath(__file__))
            api_dir = os.path.dirname(current_dir)
            temp_dir = os.path.join(api_dir, "temp_manim")
            os.makedirs(temp_dir, exist_ok=True)
            file_name = f"{class_name}.py"
            file_path = os.path.join(temp_dir, file_name)
            preview_code = f"""
from manim import *
from math import *

{code}
            """
            with open(file_path, "w") as f:
                f.write(preview_code)
            command = f"manim {file_path} {class_name} --format=png --media_dir {temp_dir} --custom_folders -pql --disable_caching"
            try:
                result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
                previews_dir = os.path.join(api_dir, "public", "previews")
                os.makedirs(previews_dir, exist_ok=True)
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                source_dir = temp_dir
                destination_dir = os.path.join(previews_dir, random_string, class_name)
                png_files = [f for f in os.listdir(source_dir) if f.endswith('.png')]
                if png_files:
                    os.makedirs(destination_dir, exist_ok=True)
                    image_list = []
                    for png_file in png_files:
                        shutil.move(os.path.join(source_dir, png_file), os.path.join(destination_dir, png_file))
                        match = re.search(r'(\d+)\.png$', png_file)
                        if match:
                            index = int(match.group(1))
                            if index % 4 == 0:
                                image_path = os.path.join(destination_dir, png_file)
                                with Image.open(image_path) as img:
                                    width, height = img.size
                                    new_width = width // 4
                                    new_height = height // 4
                                    resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                                    buffer = io.BytesIO()
                                    resized_img.save(buffer, format="PNG")
                                    base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                image_list.append({
                                    "path": image_path,
                                    "index": index,
                                    "base64": base64_image
                                })
                    image_list.sort(key=lambda x: x["index"])
                    return json.dumps({
                        "message": f"Animation preview generated. Now you will see the image frames in the next automatic message...",
                        "images": image_list
                    })
                else:
                    print(f"No PNG files found in: {source_dir}")
                    return json.dumps({
                        "error": f"No preview files generated at expected location: {source_dir}",
                        "images": []
                    })
            except subprocess.CalledProcessError as e:
                error_output = e.stdout + e.stderr
                print(f"Error running Manim command: {str(e)}")
                print(f"Command output:\n{error_output}")
                return json.dumps({
                    "error": f"ERROR. Error generating preview, please think on what could be the problem, and use `get_preview` to run the code again: {str(e)}\nCommand output:\n{error_output}",
                    "images": []
                })
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                return json.dumps({
                    "error": f"Unexpected error: {str(e)}",
                    "images": []
                })
        def generate():
            max_retries = 3
            retry_delay = 4
            while True:
                for attempt in range(max_retries):
                    try:
                        stream = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            stream=True,
                            functions=functions["openai"],
                            function_call="auto",
                        )
                        function_call_data = ""
                        function_name = ""
                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                if is_for_platform:
                                    text_obj = json.dumps({"type": "text", "text": content})
                                    yield f'{text_obj}\n'
                                else:
                                    yield content
                            elif chunk.choices[0].delta.function_call:
                                if chunk.choices[0].delta.function_call.name:
                                    function_name = chunk.choices[0].delta.function_call.name
                                    if is_for_platform:
                                        initial_call_obj = json.dumps({
                                            "type": "function_call",
                                            "content": "",
                                            "function_call": {"name": function_name}
                                        })
                                        yield f'{initial_call_obj}\n'
                                if chunk.choices[0].delta.function_call.arguments:
                                    chunk_data = chunk.choices[0].delta.function_call.arguments
                                    function_call_data += chunk_data
                                    if is_for_platform:
                                        partial_call_obj = json.dumps({
                                            "type": "function_call",
                                            "content": "",
                                            "function_call": {"args": chunk_data}
                                        })
                                        yield f'{partial_call_obj}\n'
                        break
                    except APIError as e:
                        if attempt < max_retries - 1:
                            print(f"APIError occurred: {str(e)}. Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            print(f"Max retries reached. APIError: {str(e)}")
                            yield json.dumps({"error": "Max retries reached due to API errors"})
                            return
                if function_call_data:
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": function_name,
                            "arguments": function_call_data
                        }
                    })
                    if function_name == "get_preview":
                        print(f"Calling get_preview with data: {function_call_data}")
                        args = json.loads(function_call_data)
                        result = get_preview(args['code'], args['class_name'])
                        result_json = json.loads(result)
                        function_response = {
                            "content": result_json.get("message", result_json.get("error")),
                            "name": "get_preview",
                            "role": "function"
                        }
                        messages.append(function_response)
                        if result_json.get("images"):
                            image_message = {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "ASSISTANT_MESSAGE_PREVIEW_GENERATED: This message is not generated by the user, but automatically by you, the assistant when firing the `get_preview` function, this message might not be visible to the user.\n\nThe following images are selected frames of the animation generated. Please check these frames and follow the rules: Text should not be overlapping, the space should be used efficiently, use different colors to represent different objects, plus other improvements you can think of.\n\nYou can decide now if you want to iterate on the animation (if it's too complex), or just stop here and provide the final code to the user now."
                                    }
                                ]
                            }
                            available_slots = manage_conversation_images(messages, len(result_json["images"]), engine)
                            total_frames = len(result_json["images"])
                            frame_interval = max(1, total_frames // available_slots)
                            selected_frames = result_json["images"][::frame_interval][:available_slots]
                            for image in selected_frames:
                                image_message["content"].append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image['base64']}"
                                    }
                                })
                            messages.append(image_message)
                            image_message_obj = json.dumps(image_message)
                            if not is_for_platform:
                                yield image_message_obj
                        continue
                    else:
                        break
                else:
                    break
            final_message = "\n"
            if is_for_platform:
                text_obj = json.dumps({"type": "text", "text": final_message})
                yield f'{text_obj}\n'
            else:
                yield final_message
        print("Generating response")
        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
            response.headers['x-vercel-ai-data-stream'] = 'v1'
        return response
    elif engine == "groq":
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        def get_preview(code: str, class_name: str):
            print("Generating preview (Groq)")
            current_dir = os.path.dirname(os.path.abspath(__file__))
            api_dir = os.path.dirname(current_dir)
            temp_dir = os.path.join(api_dir, "temp_manim")
            os.makedirs(temp_dir, exist_ok=True)
            file_name = f"{class_name}.py"
            file_path = os.path.join(temp_dir, file_name)
            preview_code = f"""
from manim import *
from math import *

{code}
            """
            with open(file_path, "w") as f:
                f.write(preview_code)
            command = f"manim {file_path} {class_name} --format=png --media_dir {temp_dir} --custom_folders -pql --disable_caching"
            try:
                result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
                previews_dir = os.path.join(api_dir, "public", "previews")
                os.makedirs(previews_dir, exist_ok=True)
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                source_dir = temp_dir
                destination_dir = os.path.join(previews_dir, random_string, class_name)
                png_files = [f for f in os.listdir(source_dir) if f.endswith('.png')]
                if png_files:
                    os.makedirs(destination_dir, exist_ok=True)
                    image_list = []
                    for png_file in png_files:
                        shutil.move(os.path.join(source_dir, png_file), os.path.join(destination_dir, png_file))
                        match = re.search(r'(\d+)\.png$', png_file)
                        if match:
                            index = int(match.group(1))
                            if index % 4 == 0:
                                image_path = os.path.join(destination_dir, png_file)
                                with Image.open(image_path) as img:
                                    width, height = img.size
                                    new_width = width // 4
                                    new_height = height // 4
                                    resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                                    buffer = io.BytesIO()
                                    resized_img.save(buffer, format="PNG")
                                    base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                image_list.append({
                                    "path": image_path,
                                    "index": index,
                                    "base64": base64_image
                                })
                    image_list.sort(key=lambda x: x["index"])
                    return json.dumps({
                        "message": f"Animation preview generated. Now you will see the image frames in the next automatic message...",
                        "images": image_list
                    })
                else:
                    print(f"No PNG files found in: {source_dir}")
                    return json.dumps({
                        "error": f"No preview files generated at expected location: {source_dir}",
                        "images": []
                    })
            except subprocess.CalledProcessError as e:
                error_output = e.stdout + e.stderr
                print(f"Error running Manim command: {str(e)}")
                print(f"Command output:\n{error_output}")
                return json.dumps({
                    "error": f"ERROR. Error generating preview, please think on what could be the problem, and use `get_preview` to run the code again: {str(e)}\nCommand output:\n{error_output}",
                    "images": []
                })
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                return json.dumps({
                    "error": f"Unexpected error: {str(e)}",
                    "images": []
                })
        def generate():
            max_retries = 3
            retry_delay = 4
            while True:
                for attempt in range(max_retries):
                    try:
                        stream = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            stream=True,
                            functions=functions["groq"],
                            function_call="auto",
                        )
                        function_call_data = ""
                        function_name = ""
                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                if is_for_platform:
                                    text_obj = json.dumps({"type": "text", "text": content})
                                    yield f'{text_obj}\n'
                                else:
                                    yield content
                            elif chunk.choices[0].delta.function_call:
                                if chunk.choices[0].delta.function_call.name:
                                    function_name = chunk.choices[0].delta.function_call.name
                                    if is_for_platform:
                                        initial_call_obj = json.dumps({
                                            "type": "function_call",
                                            "content": "",
                                            "function_call": {"name": function_name}
                                        })
                                        yield f'{initial_call_obj}\n'
                                if chunk.choices[0].delta.function_call.arguments:
                                    chunk_data = chunk.choices[0].delta.function_call.arguments
                                    function_call_data += chunk_data
                                    if is_for_platform:
                                        partial_call_obj = json.dumps({
                                            "type": "function_call",
                                            "content": "",
                                            "function_call": {"args": chunk_data}
                                        })
                                        yield f'{partial_call_obj}\n'
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"Groq API error: {str(e)}. Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            print(f"Max retries reached. Groq API error: {str(e)}")
                            yield json.dumps({"error": "Max retries reached due to API errors"})
                            return
                if function_call_data:
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": function_name,
                            "arguments": function_call_data
                        }
                    })
                    if function_name == "get_preview":
                        print(f"Calling get_preview with data: {function_call_data}")
                        args = json.loads(function_call_data)
                        result = get_preview(args['code'], args['class_name'])
                        result_json = json.loads(result)
                        function_response = {
                            "content": result_json.get("message", result_json.get("error")),
                            "name": "get_preview",
                            "role": "function"
                        }
                        messages.append(function_response)
                        if result_json.get("images"):
                            image_message = {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "ASSISTANT_MESSAGE_PREVIEW_GENERATED: This message is not generated by the user, but automatically by you, the assistant when firing the `get_preview` function, this message might not be visible to the user.\n\nThe following images are selected frames of the animation generated. Please check these frames and follow the rules: Text should not be overlapping, the space should be used efficiently, use different colors to represent different objects, plus other improvements you can think of.\n\nYou can decide now if you want to iterate on the animation (if it's too complex), or just stop here and provide the final code to the user now."
                                    }
                                ]
                            }
                            available_slots = manage_conversation_images(messages, len(result_json["images"]), engine)
                            total_frames = len(result_json["images"])
                            frame_interval = max(1, total_frames // available_slots)
                            selected_frames = result_json["images"][::frame_interval][:available_slots]
                            for image in selected_frames:
                                image_message["content"].append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image['base64']}"
                                    }
                                })
                            messages.append(image_message)
                            image_message_obj = json.dumps(image_message)
                            if not is_for_platform:
                                yield image_message_obj
                        continue
                    else:
                        break
                else:
                    break
            final_message = "\n"
            if is_for_platform:
                text_obj = json.dumps({"type": "text", "text": final_message})
                yield f'{text_obj}\n'
            else:
                yield final_message
        print("Generating response (Groq)")
        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
            response.headers['x-vercel-ai-data-stream'] = 'v1'
        return response
    else:
        return jsonify({"error": f"Invalid engine: {engine}"}), 400