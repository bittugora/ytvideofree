FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=change-me-in-production \
    YTVIDEOFREE_OUTPUT_DIR=/tmp

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn ytvideofree.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --proxy-headers --timeout 300 --graceful-timeout 60"]
