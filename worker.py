import os
from rq import Queue
from rq.worker import Worker
import redis
# Import the module that contains the task function
import routes.video_worker

# Debug: Print to verify the function exists
print("Checking if render_video_task exists:", hasattr(routes.video_worker, "render_video_task"))
print("Module path:", routes.video_worker.__file__)

listen = ['default']
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
conn = redis.from_url(redis_url)

if __name__ == '__main__':
    queues = [Queue(name, connection=conn) for name in listen]
    worker = Worker(queues, connection=conn)
    worker.work() 