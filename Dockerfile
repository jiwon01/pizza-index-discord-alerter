FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright system dependencies (requires root)
RUN playwright install-deps chromium

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser config.yaml .
COPY --chown=appuser:appuser main.py .
COPY --chown=appuser:appuser src/ ./src/

# Switch to appuser and install browser binaries
USER appuser
RUN playwright install chromium

# Default command
CMD ["python", "main.py"]
