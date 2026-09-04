FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# We expect the shared config and models to be mounted or copied in
# In a real build, we'd copy them. For this task, we will copy the entire v2 context or rely on local execution.
# Assuming standard single-container build where context is v2/
# COPY stage1_search/requirements.txt /app/
# RUN pip install -r /app/requirements.txt
# COPY config.py models.py /app/
# COPY stage1_search/main.py /app/stage1_search/

COPY main.py .

# Command to run
CMD ["python", "main.py"]
