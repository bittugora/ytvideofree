web: python manage.py migrate --noinput && gunicorn ytvideofree.wsgi:application --bind 0.0.0.0:${PORT:-8000} --proxy-headers
