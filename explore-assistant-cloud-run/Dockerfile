# Use the official Python image as a base image
FROM python:3.11.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the app's files into the container
WORKDIR /app
COPY requirements.txt /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY main.py /app/
COPY models.py /app/
COPY helper_functions.py /app/
COPY database.py /app/
COPY test.py /app/

EXPOSE 8080
# Set the entrypoint to run the FastAPI app
CMD ["python", "main.py"]
