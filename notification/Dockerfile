FROM python:3.11-slim
WORKDIR /app

COPY notification/requirements.txt .   
RUN pip install --no-cache-dir -r requirements.txt

COPY protos ./protos
COPY notification ./notification

RUN python -m grpc_tools.protoc -I./protos \
  --python_out=. --grpc_python_out=. ./protos/notification.proto

EXPOSE 50056
CMD [ "python", "notification/notify_server.py" ]


