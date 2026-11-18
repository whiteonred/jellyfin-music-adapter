FROM python:3.13-alpine

WORKDIR /app
COPY src/adapter.py /app/adapter.py

ENV PORT=8080
EXPOSE 8080

# Docker Compose file secrets are root-owned and mode 0600 by default.
# The adapter needs to read JELLYFIN_API_KEY_FILE at startup.
CMD ["python", "/app/adapter.py"]
