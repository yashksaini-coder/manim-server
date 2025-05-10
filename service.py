# extensions.py
import os
from flask_caching import Cache
import redis
from rq import Queue

cache = Cache()
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = redis.from_url(redis_url)
queue = Queue(connection=redis_conn)