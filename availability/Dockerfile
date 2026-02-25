FROM python:3.11-slim
WORKDIR /app

COPY availability/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY protos ./protos
COPY availability ./availability

RUN python -m grpc_tools.protoc -I./protos \
  --python_out=. --grpc_python_out=. ./protos/authentication.proto && \
  python -m grpc_tools.protoc -I./protos \
  --python_out=. --grpc_python_out=. ./protos/availability.proto 


EXPOSE 50052
CMD [ "python", "availability/avail_server.py" ]