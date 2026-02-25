"""
API Gateway (FastAPI)
---------------------
This service is the single entry point for users (Swagger UI / REST calls).

What it does:
- Accepts HTTP requests from the user
- Converts friendly inputs (like "2026-02-10 5:00 PM") into a normalized time format
- Calls internal microservices using gRPC (Create, Modify, Logging, Rating)
- Returns JSON responses back to the client
"""

import os

import grpc
from dateutil import parser
from fastapi import FastAPI, HTTPException
from google.protobuf.json_format import MessageToDict

import create_pb2
import create_pb2_grpc
import logging_pb2
import logging_pb2_grpc
import modify_pb2
import modify_pb2_grpc
import rating_pb2
import rating_pb2_grpc

app = FastAPI(title="Tutoring System API Gateway")


# -------------------- Service discovery (Docker Compose hostnames) --------------------
# These come from docker-compose.yml environment variables.
# If env vars are missing, the defaults work inside the Docker network.
CREATE_HOST = os.getenv("CREATE_HOST", "create_service:50051")
MODIFY_HOST = os.getenv("MODIFY_HOST", "modify_service:50053")
LOGGING_HOST = os.getenv("LOGGING_HOST", "logging_service:50052")
RATING_HOST = os.getenv("RATING_HOST", "rating_service:50056")


# -------------------- gRPC client stubs --------------------
# Each stub is the "client" we use to call that microservice.
create_stub = create_pb2_grpc.CreateAppointmentServiceStub(grpc.insecure_channel(CREATE_HOST))
modify_stub = modify_pb2_grpc.ModifyAppointmentServiceStub(grpc.insecure_channel(MODIFY_HOST))
logging_stub = logging_pb2_grpc.LoggingServiceStub(grpc.insecure_channel(LOGGING_HOST))
rating_stub = rating_pb2_grpc.RatingServiceStub(grpc.insecure_channel(RATING_HOST))


def pb_to_dict(msg) -> dict:
    """
    Convert a protobuf message into a JSON-friendly dictionary.
    This is how we return gRPC results to Swagger/UI as JSON.
    """
    return MessageToDict(msg, preserving_proto_field_name=True)


# -------------------- Time formatting helpers --------------------
def normalize_time(dt_str: str) -> str:
    """
    Accepts user-friendly date/time strings such as:
      - '2026-02-10 5:00 PM'
      - '2026-02-10 17:00'
      - '2026-02-10T17:00:00'

    Returns an ISO-8601 string without seconds/milliseconds changes by user:
      - stored internally like: 'YYYY-MM-DDTHH:MM:00'

    Why normalize?
    - All services store the same consistent format
    - Prevents confusion (AM/PM vs 24-hour, etc.)
    """
    dt = parser.parse(dt_str)
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


def display_time(dt_iso: str) -> str:
    """
    Convert ISO time back into a human-readable AM/PM format for UI.
    Example: '2026-02-10T17:00:00' -> '2026-02-10 05:00 PM'
    """
    dt = parser.parse(dt_iso)
    return dt.strftime("%Y-%m-%d %I:%M %p")


# -------------------- Feature 1: Book an appointment (Create Service) --------------------
@app.post("/appointments")
def create_appointment(student_id: str, tutor_id: str, start_time: str, duration_min: int):
    """
    Create a new appointment.
    This calls CreateAppointmentService (gRPC) internally.

    - Prevents double booking (enforced by Create service DB constraint)
    - Logs the event via Logging service
    """
    start_time_iso = normalize_time(start_time)

    resp = create_stub.CreateAppointment(
        create_pb2.CreateAppointmentRequest(
            student_id=student_id,
            tutor_id=tutor_id,
            start_time=start_time_iso,
            duration_min=duration_min,
        )
    )

    # If appointment_id is empty, the Create service rejected the request (e.g., double booking).
    if not resp.appointment_id:
        raise HTTPException(status_code=409, detail=resp.message or "Could not create the appointment.")

    data = pb_to_dict(resp)
    data["display_start_time"] = display_time(resp.start_time)
    return data


# -------------------- Feature 2: Cancel an appointment (Modify Service) --------------------
@app.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str):
    """
    Cancel an existing appointment.
    Calls ModifyAppointmentService.CancelAppointment (gRPC).
    """
    resp = modify_stub.CancelAppointment(modify_pb2.CancelAppointmentRequest(appointment_id=appointment_id))

    msg = (resp.message or "").lower()
    if "not found" in msg:
        raise HTTPException(status_code=404, detail=resp.message or "Appointment not found.")

    data = pb_to_dict(resp)
    if resp.start_time:
        data["display_start_time"] = display_time(resp.start_time)
    return data


# -------------------- Feature 3: Change/reschedule an appointment (Modify Service) --------------------
@app.post("/appointments/{appointment_id}/change")
def change_appointment(appointment_id: str, new_start_time: str, new_duration_min: int):
    """
    Change the time and/or duration of an existing appointment.
    Calls ModifyAppointmentService.ChangeAppointment (gRPC).

    - Also enforces no double booking (DB uniqueness constraint)
    """
    new_time_iso = normalize_time(new_start_time)

    resp = modify_stub.ChangeAppointment(
        modify_pb2.ChangeAppointmentRequest(
            appointment_id=appointment_id,
            new_start_time=new_time_iso,
            new_duration_min=new_duration_min,
        )
    )

    msg = (resp.message or "").lower()
    if "double booking" in msg:
        raise HTTPException(status_code=409, detail=resp.message or "That tutor is already booked at the new time.")
    if "not found" in msg:
        raise HTTPException(status_code=404, detail=resp.message or "Appointment not found.")

    data = pb_to_dict(resp)
    data["display_start_time"] = display_time(resp.start_time)
    return data


# -------------------- Feature: View logs (Logging Service) --------------------
@app.get("/logs/student/{student_id}")
def get_student_logs(student_id: str):
    """
    Return the appointment history logs for a specific student.
    """
    resp = logging_stub.GetStudentLogs(logging_pb2.GetStudentLogsRequest(student_id=student_id))
    return pb_to_dict(resp)


@app.get("/logs/tutor/{tutor_id}")
def get_tutor_logs(tutor_id: str):
    """
    Return the appointment history logs for a specific tutor.
    """
    resp = logging_stub.GetTutorLogs(logging_pb2.GetTutorLogsRequest(tutor_id=tutor_id))
    return pb_to_dict(resp)


# -------------------- Feature: Rate a tutor (Rating Service) --------------------
@app.post("/ratings")
def submit_rating(student_id: str, tutor_id: str, rating: int, appointment_id: str = "", comment: str = ""):
    """
    Submit a rating for a tutor (1 to 5).
    This calls RatingService.SubmitRating (gRPC).
    """
    if rating < 1 or rating > 5:
        raise HTTPException(
            status_code=400,
            detail="Rating must be an integer from 1 to 5 (1 = very poor, 5 = excellent).",
        )

    resp = rating_stub.SubmitRating(
        rating_pb2.SubmitRatingRequest(
            student_id=student_id,
            tutor_id=tutor_id,
            appointment_id=appointment_id,
            rating=rating,
            comment=comment,
            timestamp="",  # let the rating service fill timestamp if empty
        )
    )

    if not resp.ok:
        raise HTTPException(status_code=400, detail=resp.message or "Could not submit the rating.")

    return pb_to_dict(resp)


@app.get("/ratings/tutor/{tutor_id}/summary")
def tutor_rating_summary(tutor_id: str):
    """
    Summary view for a tutor:
    - average rating
    - number of ratings
    """
    resp = rating_stub.GetTutorRatingSummary(rating_pb2.TutorRequest(tutor_id=tutor_id))
    return pb_to_dict(resp)


@app.get("/ratings/tutor/{tutor_id}")
def tutor_ratings(tutor_id: str):
    """
    Detailed view for a tutor:
    - list of all ratings/reviews (most recent first)
    """
    resp = rating_stub.GetTutorRatings(rating_pb2.TutorRequest(tutor_id=tutor_id))
    return pb_to_dict(resp)
