FROM python:3.10-slim
WORKDIR /app

COPY modify_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modify_service/ .
COPY protos /protos

RUN python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/modify.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/logging.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/authentication.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/availability.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/notification.proto 

RUN mkdir -p /data
EXPOSE 50055
CMD ["python", "server.py"]
