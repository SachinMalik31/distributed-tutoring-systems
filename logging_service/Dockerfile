FROM python:3.10-slim
WORKDIR /app
COPY logging_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY logging_service/ .
COPY protos /protos

RUN python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/logging.proto

RUN mkdir -p /data
EXPOSE 50054
CMD ["python", "server.py"]
