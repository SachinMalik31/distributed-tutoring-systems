"""
Create Appointment Service (gRPC)
---------------------------------
This microservice owns ONE feature:
- Create / book a new appointment

Key responsibility:
- Prevent double booking using a DB uniqueness constraint
- Emit logs to Logging Service when an appointment is created
"""

import os
import sqlite3
import uuid
from concurrent import futures
from datetime import datetime, timezone

import grpc

import create_pb2
import create_pb2_grpc
import logging_pb2
import logging_pb2_grpc

import authentication_pb2
import authentication_pb2_grpc
import availability_pb2
import availability_pb2_grpc
import notification_pb2
import notification_pb2_grpc


DB_PATH = os.getenv("APPT_DB_PATH", "/data/appointments.db")
LOGGING_HOST = os.getenv("LOGGING_HOST", "logging_service:50054")
AUTH_ADDR = os.getenv("AUTH_ADDR", "auth:50051")
AVAIL_ADDR = os.getenv("AVAIL_ADDR", "avail:50052")
NOTIF_ADDR = os.getenv("NOTIF_ADDR", "notif:50056")


def now_iso() -> str:
    """Return current time in ISO format (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """
    Create the appointments table (if it doesn't exist).
    Also creates a UNIQUE index that blocks two active bookings for the same tutor at the same time.
    """
    
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
          appointment_id TEXT PRIMARY KEY,
          student_username TEXT NOT NULL,
          tutor_username TEXT NOT NULL,
          start_time TEXT NOT NULL,
          end_time TEXT NOT NULL,
          status TEXT NOT NULL,
          slot_id INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_tutor_time_active
        ON appointments(tutor_username, start_time, end_time)
        WHERE status='BOOKED';
        """
    )
    conn.commit()
    conn.close()


class CreateSvc(create_pb2_grpc.CreateAppointmentServiceServicer):
    """
    gRPC implementation for CreateAppointmentService.
    """

    def __init__(self):
        # Client to talk to the Logging microservice
        self.log_stub = logging_pb2_grpc.LoggingServiceStub(grpc.insecure_channel(LOGGING_HOST))
        self.auth_channel = grpc.insecure_channel(AUTH_ADDR)
        self.auth_stub = authentication_pb2_grpc.AuthenticatorStub(self.auth_channel) 
        self.avail_channel = grpc.insecure_channel(AVAIL_ADDR)
        self.avail_stub = availability_pb2_grpc.SetAvailabilityStub(self.avail_channel)
        self.notif_channel = grpc.insecure_channel(NOTIF_ADDR)
        self.notif_stub = notification_pb2_grpc.NotifierStub(self.notif_channel)

    def _log(self, appt_id: str, student_id: str, tutor_id: str, event_type: str, details: str) -> None:
        """
        Write a log entry for BOTH student and tutor.
        This makes it easy to query logs by student OR tutor later.
        """
        ts = now_iso()

        self.log_stub.LogEvent(
            logging_pb2.LogEventRequest(
                appointment_id=appt_id,
                actor_type="STUDENT",
                actor_id=student_id,
                event_type=event_type,
                details=details,
                timestamp=ts,
            )
        )

        self.log_stub.LogEvent(
            logging_pb2.LogEventRequest(
                appointment_id=appt_id,
                actor_type="TUTOR",
                actor_id=tutor_id,
                event_type=event_type,
                details=details,
                timestamp=ts,
            )
        )

    def CreateAppointment(self, request, context):
        """
        Book a new appointment.

        If the tutor is already booked at the same start_time, SQLite raises IntegrityError
        due to uniq_tutor_time_active index, and we return a friendly message.
        """
        appt_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH)

        resp = self.auth_stub.ValidateToken(authentication_pb2.ValidateTokenRequest(token=request.token))

        # Makes sure that the current user is a student
        if resp.role != authentication_pb2.STUDENT:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message="Only students can book appointments.",
            )
        

        slot_reply = self.avail_stub.GetSlot(availability_pb2.GetSlotRequest(slot_id=request.slot_id))
        if slot_reply.check == False:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message="Timeslot does not exist",
            )
        else:
            time_slot = slot_reply.slot

        if request.tutor_username != time_slot.tutor_username:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message=f"That slot belongs to tutor '{time_slot.tutor_username}', not '{request.tutor_username}'.",
            )

        # Grab information for the username provided by student
        resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=time_slot.tutor_username))

        if resp_tutor.check == False:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message="Tutor does not exist.",
            )
        
        if resp_tutor.role != authentication_pb2.TUTOR:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message="Username entered is not a tutor.",
            )
        

        resp_book =  self.avail_stub.UpdateTimeSlotStatus(availability_pb2.UpdateTimeSlotStatusRequest(old_slot_id=-1,new_slot_id=request.slot_id, is_booked='BOOKED')) 
        if resp_book.check == True:
            # Running below code and inserting into appointment
            conn.execute(
                """
                INSERT INTO appointments(appointment_id, student_username, tutor_username, start_time, end_time, status, slot_id)
                VALUES(?,?,?,?,?,'BOOKED',?)
                """,
                (appt_id, resp.username, request.tutor_username, time_slot.start_time, time_slot.end_time, time_slot.id),
            )
            conn.commit()
        else:
            return create_pb2.AppointmentResponse(
                appointment_id="",
                status="",
                message="This tutor is already booked at that time. Please choose a different time.",
            )
        conn.close()
        self.notif_stub.SendBookingConfirmation(notification_pb2.SendBookingConfirmationRequest(
            user_email = resp.email,
            tutor_email = resp_tutor.email,
            user_username = resp.username,
            tutor_username = request.tutor_username,
            start_time = time_slot.start_time,
            end_time = time_slot.end_time,
            appointment_id = appt_id,
        ))
        return create_pb2.AppointmentResponse(
            appointment_id=appt_id,
            student_username=resp.username,
            tutor_username=request.tutor_username,
            start_time=time_slot.start_time,
            end_time=time_slot.end_time,
            status="BOOKED",
            slot_id=time_slot.id,
            message="Appointment successfully created.",
        )

def serve() -> None:
    """Start the gRPC server on port 50053."""
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    create_pb2_grpc.add_CreateAppointmentServiceServicer_to_server(CreateSvc(), server)
    server.add_insecure_port("[::]:50053")
    server.start()
    print("CreateAppointmentService is running on port 50053.", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
