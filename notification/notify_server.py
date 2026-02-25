import os
import smtplib
from email.message import EmailMessage
from concurrent import futures
import grpc
import sys
from datetime import datetime  

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import notification_pb2
import notification_pb2_grpc

SMTP_HOST = os.environ.get("SMTP_HOST", "mailhog")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@tutoring.local")
USE_TLS = os.environ.get("SMTP_TLS", "0") == "1"
USER_FRIENDLY_FMT = "%Y-%m-%d %I:%M %p"  # e.g. 2026-02-25 12:30 PM

def fmt_time(s: str) -> str:
    """
    Convert ISO datetime string to user-friendly format for display.
    If parsing fails, return original string (safe fallback).
    """
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime(USER_FRIENDLY_FMT)
    except ValueError:
        return s
    
def send_email(to_addr: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        if USE_TLS:
            s.starttls()
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


class Notifier(notification_pb2_grpc.NotifierServicer):
    def SendBookingConfirmation(self, request, context):
        try:
            subject = f"Booking Confirmed (Appt {request.appointment_id})"
            student_body = (
                f"Hi {request.user_username},\n\n"
                f"Your appointment is confirmed.\n"
                f"Tutor: {request.tutor_username}\n"
                f"When: {fmt_time(request.start_time)} to {fmt_time(request.end_time)}\n"
                f"Appointment ID: {request.appointment_id}\n\n"
                f"Thanks!"
            )
            tutor_body = (
                f"Hi {request.tutor_username},\n\n"
                f"You have a new booking.\n"
                f"Student: {request.user_username}\n"
                f"When: {fmt_time(request.start_time)} to {fmt_time(request.end_time)}\n"
                f"Appointment ID: {request.appointment_id}\n\n"
                f"Thanks!"
            )

            send_email(request.user_email, subject, student_body)
            send_email(request.tutor_email, subject, tutor_body)

            return notification_pb2.NotificationReply(check=True, message="emails sent")
        except Exception as e:
            return notification_pb2.NotificationReply(check=False, message=f"failed: {e}")

    def SendCancellationNotice(self, request, context):
        try:
            subject = f"Appointment Cancelled (Appt {request.appointment_id})"
            who = request.cancelled_by or "unknown"

            body_common = (
                f"Appointment cancelled.\n"
                f"Student: {request.user_username}\n"
                f"Tutor: {request.tutor_username}\n"
                f"When: {fmt_time(request.start_time)} to {fmt_time(request.end_time)}\n"
                f"Appointment ID: {request.appointment_id}\n"
                f"Cancelled by: {who}\n"
            )

            send_email(request.user_email, subject, "Hi,\n\n" + body_common)
            send_email(request.tutor_email, subject, "Hi,\n\n" + body_common)

            return notification_pb2.NotificationReply(check=True, message="emails sent")
        except Exception as e:
            return notification_pb2.NotificationReply(check=False, message=f"failed: {e}")


def serve():
    port = "50056"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    notification_pb2_grpc.add_NotifierServicer_to_server(Notifier(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print(f"Notification Service started, listening on {port} SMTP={SMTP_HOST}:{SMTP_PORT}",flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()