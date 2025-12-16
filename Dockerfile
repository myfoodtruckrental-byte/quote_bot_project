# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install jinja2

# Copy the rest of the application's code into the container at /app
COPY . .

# The CMD is specified in docker-compose.yml
# This Dockerfile can be used for both the bot and the api
