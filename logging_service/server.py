"""
Logging Service (gRPC)
----------------------
This microservice stores audit logs for appointments.

Why it exists as a separate service:
- Booking/modify services stay focused on business logic
- Logging can scale independently
- You can query student logs and tutor logs without touching booking DB
"""

import os
import sqlite3
from concurrent import futures
from datetime import datetime, timezone

import grpc

import logging_pb2
import logging_pb2_grpc


DB_PATH = os.getenv("LOG_DB_PATH", "/data/logging.db")


def now_iso() -> str:
    """Return current time in ISO format (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """
    Create the logs table (if needed) and indexes for faster queries.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          appointment_id TEXT NOT NULL,
          actor_type TEXT NOT NULL,
          actor_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          details TEXT NOT NULL,
          timestamp TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_student ON logs(actor_type, actor_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_tutor ON logs(actor_type, actor_id);")
    conn.commit()
    conn.close()


class LoggingService(logging_pb2_grpc.LoggingServiceServicer):
    """gRPC implementation of LoggingService."""

    def LogEvent(self, request, context):
        """
        Store a single log entry in SQLite.
        If timestamp is not provided, we automatically fill it with current UTC time.
        """
        ts = request.timestamp or now_iso()
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO logs(appointment_id, actor_type, actor_id, event_type, details, timestamp)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    request.appointment_id,
                    request.actor_type,
                    request.actor_id,
                    request.event_type,
                    request.details,
                    ts,
                ),
            )
            conn.commit()
            return logging_pb2.LogEventResponse(ok=True, message="Log recorded successfully.")
        finally:
            conn.close()

    def GetStudentLogs(self, request, context):
        """
        Return logs for a student (newest first).
        """
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT appointment_id, event_type, details, timestamp
                FROM logs
                WHERE actor_type='STUDENT' AND actor_id=?
                ORDER BY timestamp DESC
                """,
                (request.student_id,),
            ).fetchall()

            items = [
                logging_pb2.LogItem(appointment_id=r[0], event_type=r[1], details=r[2], timestamp=r[3])
                for r in rows
            ]
            return logging_pb2.LogsResponse(items=items)
        finally:
            conn.close()

    def GetTutorLogs(self, request, context):
        """
        Return logs for a tutor (newest first).
        """
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT appointment_id, event_type, details, timestamp
                FROM logs
                WHERE actor_type='TUTOR' AND actor_id=?
                ORDER BY timestamp DESC
                """,
                (request.tutor_id,),
            ).fetchall()

            items = [
                logging_pb2.LogItem(appointment_id=r[0], event_type=r[1], details=r[2], timestamp=r[3])
                for r in rows
            ]
            return logging_pb2.LogsResponse(items=items)
        finally:
            conn.close()


def serve() -> None:
    """Start the gRPC server on port 50054."""
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    logging_pb2_grpc.add_LoggingServiceServicer_to_server(LoggingService(), server)
    server.add_insecure_port("[::]:50054")
    server.start()
    print("LoggingService is running on port 50054.", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
