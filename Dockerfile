FROM python:3.10-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port (default 8080)
EXPOSE 8080

# Example: docker run -e OPENAI_API_KEY=sk-... -e GROQ_API_KEY=... -p 8080:8080 generative-manim-api
CMD ["gunicorn", "-b", "0.0.0.0:8080", "run:app"] 