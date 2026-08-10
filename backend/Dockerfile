FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binary
RUN playwright install chromium --with-deps

# Copy the rest of the backend code
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the FastAPI server via uvicorn (no --reload for production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
