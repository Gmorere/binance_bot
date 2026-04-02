FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BOT_CONFIG_PATH=/app/config/base.yaml
ENV BOT_BASE_DIR=/app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data/raw /app/data/processed /app/outputs

CMD ["python", "run_paper.py"]
