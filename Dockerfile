FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY app.py .
COPY static ./static
ENV HOST=0.0.0.0 TZ=Asia/Shanghai
EXPOSE 8765
CMD ["python", "-u", "app.py"]
