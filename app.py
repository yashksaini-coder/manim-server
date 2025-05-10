import os
from flask import Flask, send_from_directory, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from flask_caching import Cache
from service import cache, redis_conn, queue
import redis
from rq import Queue

# Load environment variables from .env file
load_dotenv()

# Import blueprints from routes
from routes.video_rendering import video_rendering_bp
from routes.code_generation import code_generation_bp
# Initialize Flask app
app = Flask(__name__, static_folder="public", static_url_path="/public")

# Register all blueprints (endpoints)
app.register_blueprint(video_rendering_bp)
app.register_blueprint(code_generation_bp)
# Enable CORS for all routes
CORS(app)

# Flask-Caching config for Redis
app.config['CACHE_TYPE'] = 'redis'
app.config['CACHE_REDIS_HOST'] = os.getenv('REDIS_HOST', 'localhost')
app.config['CACHE_REDIS_PORT'] = int(os.getenv('REDIS_PORT', 6379))
app.config['CACHE_REDIS_DB'] = int(os.getenv('REDIS_DB', 0))
app.config['CACHE_DEFAULT_TIMEOUT'] = 300

cache.init_app(app)

# Redis connection and RQ queue
redis_url = os.getenv('REDIS_URL', f"redis://{app.config['CACHE_REDIS_HOST']}:{app.config['CACHE_REDIS_PORT']}/{app.config['CACHE_REDIS_DB']}")
redis_conn = redis.from_url(redis_url)
queue = Queue(connection=redis_conn)

@app.route("/")
def hello_world():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
