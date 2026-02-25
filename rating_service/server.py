"""
Rating Service (gRPC)
---------------------
This microservice owns ONE feature:
- Students can rate tutors on a 1 to 5 integer scale

It supports:
- SubmitRating: add a rating/review
- GetTutorRatingSummary: average rating + count
- GetTutorRatings: list of all reviews for a tutor
"""

import os
import sqlite3
from concurrent import futures
from datetime import datetime, timezone

import grpc

import rating_pb2
import rating_pb2_grpc

import authentication_pb2
import authentication_pb2_grpc


DB_PATH = os.getenv("RATING_DB_PATH", "/data/rating.db")
AUTH_ADDR = os.getenv("AUTH_ADDR", "auth:50051")


def now_iso() -> str:
    """Return current time in ISO format (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """
    Create ratings table + helpful indexes.
    Unique constraint ensures a student can rate the same appointment only once (if appointment_id is provided).
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ratings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tutor_username TEXT NOT NULL,
          student_username TEXT NOT NULL,
          appointment_id TEXT,
          rating INTEGER NOT NULL,
          comment TEXT,
          timestamp TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_student_appt
        ON ratings(student_username, appointment_id)
        WHERE appointment_id IS NOT NULL;
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tutor ON ratings(tutor_username);")
    conn.commit()
    conn.close()


class RatingSvc(rating_pb2_grpc.RatingServiceServicer):
    """gRPC implementation of RatingService."""
    def __init__(self):
        # Client to talk to the Logging microservice
        self.auth_channel = grpc.insecure_channel(AUTH_ADDR)
        self.auth_stub = authentication_pb2_grpc.AuthenticatorStub(self.auth_channel) 


    def SubmitRating(self, request, context):
        """
        Store one rating entry.
        Rules:
        - rating must be between 1 and 5
        - if appointment_id provided, a student can rate that appointment only once
        """
        if request.rating < 1 or request.rating > 5:
            return rating_pb2.SubmitRatingResponse(
                ok=False,
                message="Rating must be an integer from 1 to 5 (1 = very poor, 5 = excellent).",
            )

        ts = request.timestamp or now_iso()
        conn = sqlite3.connect(DB_PATH)

        # Check if request.tutor_username exists in database and if it is actaully tutor
        # Grab information for the username provided by student
        resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=request.tutor_username))

        if resp_tutor.check == False:
            return rating_pb2.SubmitRatingResponse(ok=False, message="Tutor does not exist")
        
        if resp_tutor.role != authentication_pb2.TUTOR:
            return rating_pb2.SubmitRatingResponse(ok=False, message="Name entered is not a tutor")

        try:
            try:
                conn.execute(
                    """
                    INSERT INTO ratings(tutor_username, student_username, appointment_id, rating, comment, timestamp)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        request.tutor_username,
                        request.student_username,
                        request.appointment_id or None,
                        request.rating,
                        request.comment,
                        ts,
                    ),
                )
                conn.commit()
                return rating_pb2.SubmitRatingResponse(ok=True, message="Thank you! Your rating was submitted.")
            except sqlite3.IntegrityError:
                return rating_pb2.SubmitRatingResponse(
                    ok=False,
                    message="It looks like you already rated this appointment.",
                )
        finally:
            conn.close()

    def GetTutorRatingSummary(self, request, context):
        """
        Return average rating and rating count for a tutor.
        """
        conn = sqlite3.connect(DB_PATH)

        resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=request.tutor_username))

        if resp_tutor.check == False:
            return rating_pb2.TutorRatingSummary(ok=False, message="Tutor does not exist")
        
        if resp_tutor.role != authentication_pb2.TUTOR:
            return rating_pb2.TutorRatingSummary(ok=False, message="Name entered is not a tutor")

        try:
            row = conn.execute(
                "SELECT AVG(rating), COUNT(*) FROM ratings WHERE tutor_username=?",
                (request.tutor_username,),
            ).fetchone()

            if row is None:
                return rating_pb2.TutorRatingSummary(
                    ok=False,
                    message="Rating does not exist",
                    tutor_username="",
                    average_rating=0,
                    rating_count=0,
                )

            avg = float(row[0]) if row[0] is not None else 0.0
            cnt = int(row[1])

            return rating_pb2.TutorRatingSummary(
                ok=True,
                tutor_username=request.tutor_username,
                average_rating=avg,
                rating_count=cnt,
            )
        finally:
            conn.close()

    def GetTutorRatings(self, request, context):
        """
        Return detailed list of reviews/ratings for a tutor (most recent first).
        """
        conn = sqlite3.connect(DB_PATH)

        resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=request.tutor_username))

        if resp_tutor.check == False:
            return rating_pb2.TutorRatingsResponse(ok=False, message="Tutor does not exist")
        
        if resp_tutor.role != authentication_pb2.TUTOR:
            return rating_pb2.TutorRatingsResponse(ok=False, message="Name entered is not a tutor")

        try:
            rows = conn.execute(
                """
                SELECT student_username, appointment_id, rating, COALESCE(comment,''), timestamp
                FROM ratings
                WHERE tutor_username=?
                ORDER BY timestamp DESC
                """,
                (request.tutor_username,),
            ).fetchall()

            if rows is None:
                return rating_pb2.TutorRatingsResponse(ok=False,message='No ratings')

            items = [
                rating_pb2.TutorRatingItem(
                    student_username=r[0],
                    appointment_id=r[1] or "",
                    rating=r[2],
                    comment=r[3],
                    timestamp=r[4],
                )
                for r in rows
            ]
            return rating_pb2.TutorRatingsResponse(ok=True,items=items)
        finally:
            conn.close()


def serve() -> None:
    """Start the gRPC server on port 50057."""
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rating_pb2_grpc.add_RatingServiceServicer_to_server(RatingSvc(), server)
    server.add_insecure_port("[::]:50057")
    server.start()
    print("RatingService is running on port 50057.", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
