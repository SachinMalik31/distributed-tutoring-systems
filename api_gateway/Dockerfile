FROM python:3.10-slim
WORKDIR /app
COPY api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_gateway/ .
COPY protos /protos

RUN python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/create.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/modify.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/logging.proto && \
  python -m grpc_tools.protoc -I/protos \
  --python_out=. --grpc_python_out=. /protos/rating.proto


EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
