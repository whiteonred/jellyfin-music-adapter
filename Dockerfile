FROM python:3.13-alpine

WORKDIR /app
COPY src/adapter.py /app/adapter.py

ENV PORT=8080
EXPOSE 8080

USER 65532:65532
CMD ["python", "/app/adapter.py"]
