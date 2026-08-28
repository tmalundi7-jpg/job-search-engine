FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps

COPY . .

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
