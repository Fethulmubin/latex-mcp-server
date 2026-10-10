FROM python:3.11-slim

# Install system utilities, font caches, and Tectonic compiler
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fontconfig \
    && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh \
    && mv tectonic /usr/local/bin/ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV PYTHONUNBUFFERED=1
ENV MCP_TRANSPORT=sse

# FastMCP defaults to listening on port 8000 if PORT is not set
EXPOSE 8000

CMD ["python", "server.py"]