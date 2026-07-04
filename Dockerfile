FROM python:3.11-slim-bookworm

# Install system dependencies for pyodbc and msodbcsql18
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Add Microsoft repository and install msodbcsql18
# We use Debian 12 (bookworm) since python:3.11-slim is based on bookworm
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Railway provides the PORT environment variable
ENV PORT=8080
EXPOSE $PORT

# Start the application using the same command from railway.toml
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
