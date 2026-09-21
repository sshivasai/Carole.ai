FROM python:3.11-slim

WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
ENV CAROLE_HOME_DIR=/data/carole

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
RUN adduser --disabled-password --gecos '' appuser && mkdir -p /data/carole && chown -R appuser /app /data /opt/playwright
USER appuser

# Expose port
EXPOSE 8000

# Run the FastAPI server via uvicorn (no --reload for production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
