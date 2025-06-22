# Use the official Python slim base image
FROM python:3.10-slim

# Set a reliable working directory
WORKDIR /app

# Copy only requirements first for better caching
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application codes
COPY app.py ./

# Expose the port the app runs on
EXPOSE 8080

# Define the default command
CMD ["python", "app.py"]
