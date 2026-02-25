FROM python:3.10-slim
WORKDIR /app

COPY rating_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rating_service/ .
COPY protos /protos

RUN python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/rating.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/authentication.proto

RUN mkdir -p /data
EXPOSE 50057
CMD ["python", "server.py"]
