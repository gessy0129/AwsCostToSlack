FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script files
COPY . .

# Set the entrypoint
ENTRYPOINT ["python", "cost_analysis.py"]
