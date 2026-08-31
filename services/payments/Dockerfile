FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY packages/common /packages/common
COPY packages/contracts /packages/contracts
COPY packages/observability /packages/observability
COPY packages/chaos /packages/chaos

RUN pip install --no-cache-dir \
    /packages/common \
    /packages/contracts \
    /packages/observability \
    /packages/chaos

COPY services/payments/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/payments/app ./app

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
