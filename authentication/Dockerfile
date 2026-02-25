FROM python:3.11-slim
WORKDIR /app

COPY authentication/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY protos ./protos
COPY authentication ./authentication

RUN python -m grpc_tools.protoc -I./protos \
  --python_out=. --grpc_python_out=. ./protos/authentication.proto

EXPOSE 50051
CMD [ "python", "authentication/auth_server.py" ]