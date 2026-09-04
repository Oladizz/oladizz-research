FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Note: In a real deploy, the config.py and models.py would be copied via context, 
# but for this script we assume they are accessible or copied beforehand.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
