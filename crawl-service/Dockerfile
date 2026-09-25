# Crawl service — image độc lập, tự chạy được 1 mình (đúng tinh thần
# microservice: build/deploy/scale riêng, không phụ thuộc service khác).
FROM python:3.12-slim

WORKDIR /app

# Cài dependency trước để tận dụng Docker layer cache (đổi code không phải
# cài lại thư viện).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY data/fixtures/ data/fixtures/

WORKDIR /app/src
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
