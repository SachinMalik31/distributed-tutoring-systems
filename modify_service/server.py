"""
Modify Appointment Service (gRPC)
---------------------------------
This microservice owns ONE feature:
- Change or cancel an existing appointment

Key responsibility:
- Cancel: marks status as CANCELED
- Change: updates time/duration and blocks double booking via the same uniqueness constraint
- Emits logs to Logging Service for traceability
"""

import os
import sqlite3
from concurrent import futures
from datetime import datetime, timezone

import grpc

import logging_pb2
import logging_pb2_grpc
import modify_pb2
import modify_pb2_grpc

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
    Ensure appointments table + uniqueness constraint exists.
    This service shares the same DB volume as Create service.
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


class ModifySvc(modify_pb2_grpc.ModifyAppointmentServiceServicer):
    """gRPC implementation for ModifyAppointmentService."""

    def __init__(self):
        self.log_stub = logging_pb2_grpc.LoggingServiceStub(grpc.insecure_channel(LOGGING_HOST))
        self.auth_channel = grpc.insecure_channel(AUTH_ADDR)
        self.auth_stub = authentication_pb2_grpc.AuthenticatorStub(self.auth_channel) 
        self.avail_channel = grpc.insecure_channel(AVAIL_ADDR)
        self.avail_stub = availability_pb2_grpc.SetAvailabilityStub(self.avail_channel)
        self.notif_channel = grpc.insecure_channel(NOTIF_ADDR)
        self.notif_stub = notification_pb2_grpc.NotifierStub(self.notif_channel)

    def _log(self, appt_id: str, student_id: str, tutor_id: str, event_type: str, details: str) -> None:
        """Write the same event to both student logs and tutor logs."""
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

    def CancelAppointment(self, request, context):
        """
        Cancel appointment by appointment_id.
        If already canceled, return a friendly response (idempotent cancel).
        """
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                """
                SELECT appointment_id, student_username, tutor_username, start_time, end_time, status, slot_id
                FROM appointments WHERE appointment_id=?
                """,
                (request.appointment_id,),
            ).fetchone()

            if not row:
                return modify_pb2.AppointmentResponse(message="Appointment not found. Please check the appointment ID.")
            
            resp = self.auth_stub.ValidateToken(authentication_pb2.ValidateTokenRequest(token=request.token))


            if resp.username != row[1]:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    student_username=row[1],
                    tutor_username=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    status=row[5],
                    slot_id=row[6],
                    message="Cannot cancel appointment. You did not make this appointment.",
                )


            if row[5] == "CANCELED":
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    student_username=row[1],
                    tutor_username=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    status=row[5],
                    slot_id=row[6],
                    message="This appointment was already canceled.",
                )
            
            resp_book =  self.avail_stub.UpdateTimeSlotStatus(availability_pb2.UpdateTimeSlotStatusRequest(old_slot_id=-1,new_slot_id=row[6], is_booked='CANCELED')) # return a bool and a message
            if resp_book.check == False:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    student_username=row[1],
                    tutor_username=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    status=row[5],
                    slot_id=row[6],
                    message=resp_book.message,
                )
            conn.execute("UPDATE appointments SET status='CANCELED' WHERE appointment_id=?", (request.appointment_id,))
            conn.commit()

            self._log(row[0], row[1], row[2], "CANCELED", f"Appointment canceled (was scheduled at {row[3]}).")

            resp_student = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=row[1]))
            resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=row[2]))

            self.notif_stub.SendCancellationNotice(notification_pb2.SendCancellationNoticeRequest(
                user_email = resp_student.email,
                tutor_email = resp_tutor.email,
                user_username = row[1],
                tutor_username = row[2],
                start_time = row[3],
                end_time = row[4],
                appointment_id = row[0],
                cancelled_by=row[1],
            ))

            return modify_pb2.AppointmentResponse(
                appointment_id=row[0],
                student_username=row[1],
                tutor_username=row[2],
                start_time=row[3],
                end_time=row[4],
                status="CANCELED",
                slot_id=row[6],
                message="Appointment canceled successfully.",
            )
        finally:
            conn.close()

    def ChangeAppointment(self, request, context):
        """
        Reschedule an appointment.
        Blocks double booking using the same DB uniqueness constraint as Create service.
        """
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                """
                SELECT appointment_id, student_username, tutor_username, start_time, end_time, status, slot_id
                FROM appointments WHERE appointment_id=?
                """,
                (request.appointment_id,),
            ).fetchone()

            if not row:
                return modify_pb2.AppointmentResponse(message="Appointment not found. Please check the appointment ID.")

            resp = self.auth_stub.ValidateToken(authentication_pb2.ValidateTokenRequest(token=request.token))


            if resp.username != row[1]:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="Cannot change appointment. You did not make this appointment.",
                )

            if row[5] == "CANCELED":
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="This appointment is canceled, so it cannot be changed.",
                )
            
            if request.new_slot_id == request.old_slot_id:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="New Slot ID cannot be same as Old Slot ID",
                )

            old_slot_reply = self.avail_stub.GetSlot(availability_pb2.GetSlotRequest(slot_id=request.old_slot_id))
            if old_slot_reply.check == False:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="Time Slot Does Not Exist",
                )
            else:
                old_time_slot = old_slot_reply.slot


            new_slot_reply = self.avail_stub.GetSlot(availability_pb2.GetSlotRequest(slot_id=request.new_slot_id))
            if new_slot_reply.check == False:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="Time Slot Does Not Exist",
                )
            else:
                new_time_slot = new_slot_reply.slot

            if new_time_slot.tutor_username != old_time_slot.tutor_username:
                return modify_pb2.AppointmentResponse(
                    appointment_id=row[0],
                    status="CANCELED",
                    message="Must select new time slot from same tutor. To book with a different tutor, cancel appointment with current tutor then book new appointment with new tutor.",
                )

            resp_time_slot = self.avail_stub.UpdateTimeSlotStatus(availability_pb2.UpdateTimeSlotStatusRequest(old_slot_id=request.old_slot_id,new_slot_id=request.new_slot_id, is_booked='CHANGED')) 
            if resp_time_slot.check == True:
                try:
                    conn.execute(
                        "UPDATE appointments SET start_time=?, end_time=?, slot_id=? WHERE appointment_id=?",
                        (new_time_slot.start_time, new_time_slot.end_time, request.new_slot_id, request.appointment_id),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    return modify_pb2.AppointmentResponse(
                        appointment_id=row[0],
                        student_username=row[1],
                        tutor_username=row[2],
                        start_time=new_time_slot.start_time,
                        end_time=new_time_slot.end_time,
                        status=row[5],
                        message="That tutor is already booked at the new time. Please choose another time.",
                    )
                
            resp_student = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=row[1]))
            resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=row[2]))
            
            self.notif_stub.SendCancellationNotice(notification_pb2.SendCancellationNoticeRequest(
                user_email = resp_student.email,
                tutor_email = resp_tutor.email,
                user_username = row[1],
                tutor_username = row[2],
                start_time = old_time_slot.start_time,
                end_time = old_time_slot.end_time,
                appointment_id = row[0],
                cancelled_by=row[1],
            ))
            
            self.notif_stub.SendBookingConfirmation(notification_pb2.SendBookingConfirmationRequest(
                user_email = resp_student.email,
                tutor_email = resp_tutor.email,
                user_username = row[1],
                tutor_username = row[2],
                start_time = new_time_slot.start_time,
                end_time = new_time_slot.end_time,
                appointment_id = row[0],
            ))

            self._log(
                row[0],
                row[1],
                row[2],
                "CHANGED",
                f"Appointment rescheduled from {old_time_slot.start_time} to {new_time_slot.start_time}.",
            )

            return modify_pb2.AppointmentResponse(
                appointment_id=row[0],
                student_username=row[1],
                tutor_username=row[2],
                start_time=new_time_slot.start_time,
                end_time=new_time_slot.end_time,
                status="BOOKED",
                slot_id=request.new_slot_id,
                message="Appointment changed successfully.",
            )
        finally:
            conn.close()

    def GetAppointment(self, request, context):
        """
        Simple lookup endpoint by appointment_id.
        Helpful for debugging and demos.
        """
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                """
                SELECT appointment_id, student_username, tutor_username, start_time, end_time, status, slot_id
                FROM appointments WHERE appointment_id=?
                """,
                (request.appointment_id,),
            ).fetchone()

            if not row:
                return modify_pb2.AppointmentResponse(message="Appointment not found. Please check the appointment ID.")

            return modify_pb2.AppointmentResponse(
                appointment_id=row[0],
                student_username=row[1],
                tutor_username=row[2],
                start_time=row[3],
                end_time=row[4],
                status=row[5],
                slot_id=row[6],
                message="Appointment details retrieved successfully.",
            )
        finally:
            conn.close()


def serve() -> None:
    """Start the gRPC server on port 50055."""
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    modify_pb2_grpc.add_ModifyAppointmentServiceServicer_to_server(ModifySvc(), server)
    server.add_insecure_port("[::]:50055")
    server.start()
    print("ModifyAppointmentService is running on port 50055.", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
