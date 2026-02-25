#!/usr/bin/env python3
"""
CLI Client for Tutor Booking Microservices (gRPC)

Services / ports:
Auth          -> localhost:50051
Availability  -> localhost:50052
Create        -> localhost:50053
Modify        -> localhost:50055
Notification  -> localhost:50056 (not used here)
Rating        -> localhost:50057

✅ What this script does
- Start menu: register student, register tutor, login, exit
- After login:
  - Student menu: browse tutors/slots, create appt, modify appt (get/cancel/change), rate tutor, logout
  - Tutor menu: add/remove availability slots, logout
"""

from __future__ import annotations

import sys
import getpass
from dataclasses import dataclass
from typing import Optional
from datetime import datetime  

import grpc
from google.protobuf import empty_pb2  

# =========================
# Auth
# =========================
import authentication_pb2 as auth_pb2
import authentication_pb2_grpc as auth_grpc

# Availability
import availability_pb2 as avail_pb2
import availability_pb2_grpc as avail_grpc

# Create
import create_pb2 as create_pb2
import create_pb2_grpc as create_grpc

# Modify
import modify_pb2 as modify_pb2
import modify_pb2_grpc as modify_grpc

# Rating
import rating_pb2 as rating_pb2
import rating_pb2_grpc as rating_grpc


# =========================
# Config
# =========================
AUTH_ADDR = "localhost:50051"
AVAIL_ADDR = "localhost:50052"
CREATE_ADDR = "localhost:50053"
MODIFY_ADDR = "localhost:50055"
RATING_ADDR = "localhost:50057"


# =========================
# Helpers
# =========================
USER_FRIENDLY_FMT = "%Y-%m-%d %I:%M %p"  # e.g. 2026-02-25 12:30 PM


def to_iso(dt_str: str) -> str:
    """
    Convert user-friendly datetime string -> ISO 8601 string (seconds precision).
    Input:  '2026-02-25 12:30 PM'
    Output: '2026-02-25T12:30:00'

    Bonus: if user already enters ISO ('2026-02-25T12:30:00'), we accept it too.
    """
    s = dt_str.strip()
    if not s:
        raise ValueError("Empty datetime string")

    # If user already gives ISO, accept it
    try:
        dt = datetime.fromisoformat(s)
        return dt.isoformat(timespec="seconds")
    except ValueError:
        pass

    # Otherwise parse friendly format
    dt = datetime.strptime(s, USER_FRIENDLY_FMT)
    return dt.isoformat(timespec="seconds")

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


def fmt_range(start_iso: str, end_iso: str) -> str:
    """Return 'START -> END' in user-friendly format."""
    return f"{fmt_time(start_iso)} -> {fmt_time(end_iso)}"


def prompt(msg: str) -> str:
    return input(msg).strip()


def prompt_int(msg: str) -> int:
    while True:
        s = input(msg).strip()
        try:
            return int(s)
        except ValueError:
            print("Please enter a valid integer.")


def prompt_password(msg: str = "Password: ") -> str:
    return getpass.getpass(msg)


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def show_rpc_error(e: grpc.RpcError) -> None:
    code = e.code()
    details = e.details()
    print(f"[gRPC ERROR] {code}: {details}")


def choose_menu(title: str, options: list[tuple[str, str]]) -> str:
    """
    options: list of (key, label)
    returns chosen key
    """
    print_header(title)
    for key, label in options:
        print(f"{key}) {label}")
    while True:
        choice = input("Choose: ").strip()
        valid = {k for k, _ in options}
        if choice in valid:
            return choice
        print(f"Invalid choice. Options: {', '.join(sorted(valid))}")


@dataclass
class Session:
    token: Optional[str] = None
    username: Optional[str] = None
    role: Optional[int] = None  # auth_pb2.Role enum value


# =========================
# Client Wrapper
# =========================
class Client:
    def __init__(self) -> None:
        # Create channels
        self.auth_channel = grpc.insecure_channel(AUTH_ADDR)
        self.avail_channel = grpc.insecure_channel(AVAIL_ADDR)
        self.create_channel = grpc.insecure_channel(CREATE_ADDR)
        self.modify_channel = grpc.insecure_channel(MODIFY_ADDR)
        self.rating_channel = grpc.insecure_channel(RATING_ADDR)

        # Stubs
        self.auth = auth_grpc.AuthenticatorStub(self.auth_channel)
        self.avail = avail_grpc.SetAvailabilityStub(self.avail_channel)
        self.create = create_grpc.CreateAppointmentServiceStub(self.create_channel)
        self.modify = modify_grpc.ModifyAppointmentServiceStub(self.modify_channel)
        self.rating = rating_grpc.RatingServiceStub(self.rating_channel)

        self.session = Session()

    # -------------------------
    # Auth flows
    # -------------------------
    def register_student(self) -> None:
        print_header("Register Student")
        firstname = prompt("First name: ")
        lastname = prompt("Last name: ")
        username = prompt("Username: ")
        email = prompt("Email: ").lower()
        password = prompt("Password: ")  

        req = auth_pb2.RegisterUserRequest(
            firstname=firstname,
            lastname=lastname,
            username=username,
            email=email,
            password=password,
            role=auth_pb2.STUDENT,
            tutor_code="",  # not used for student
        )
        try:
            resp = self.auth.RegisterUser(req)
            print(resp.message)
            if resp.check and resp.token:
                print(f"Token: {resp.token}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def register_tutor(self) -> None:
        print_header("Register Tutor")
        firstname = prompt("First name: ")
        lastname = prompt("Last name: ")
        username = prompt("Username: ")
        email = prompt("Email: ").lower()
        password = prompt("Password: ") 
        tutor_code = prompt("Tutor code (if required by your server, else leave blank): ")

        req = auth_pb2.RegisterUserRequest(
            firstname=firstname,
            lastname=lastname,
            username=username,
            email=email,
            password=password,
            role=auth_pb2.TUTOR,
            tutor_code=tutor_code,
        )
        try:
            resp = self.auth.RegisterUser(req)
            print(resp.message)
            if resp.check and resp.token:
                print(f"Token: {resp.token}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def login(self) -> bool:
        print_header("Login")
        user = prompt("Username or email: ")
        password = prompt("Password: ")  

        req = auth_pb2.LoginRequest(username_or_email=user, password=password)
        try:
            resp = self.auth.Login(req)
            print(resp.message)

            if not resp.check or not resp.token:
                return False

            self.session.token = resp.token
            self.session.role = resp.role

            # Fetch username (and other info) using ValidateToken
            vreq = auth_pb2.ValidateTokenRequest(token=self.session.token)
            vresp = self.auth.ValidateToken(vreq)
            if vresp.check:
                self.session.username = vresp.username
                self.session.role = vresp.role  # trust ValidateToken
            else:
                print(vresp.message)
            return True
        except grpc.RpcError as e:
            show_rpc_error(e)
            return False

    def logout(self) -> None:
        if not self.session.token:
            return
        try:
            resp = self.auth.Logout(auth_pb2.LogoutRequest(token=self.session.token))
            print(resp.message)
        except grpc.RpcError as e:
            show_rpc_error(e)
        finally:
            self.session = Session()

    # -------------------------
    # Availability (Tutor & Student)
    # -------------------------
    def list_all_tutors_with_slots(self) -> None:
        print_header("Tutors With Available Time Slots")
        try:
            resp = self.avail.ListAllTutorsWithTimeSlots(empty_pb2.Empty())
            if not resp.tutor_username:
                print("(none)")
                return
            for t in resp.tutor_username:
                print(f"- {t}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def list_all_time_slots(self) -> None:
        print_header("All Time Slots")
        try:
            resp = self.avail.ListAllTimeSlots(empty_pb2.Empty())
            if not resp.slot:
                print("(none)")
                return
            for s in resp.slot:
                print(f"[{s.id}] tutor={s.tutor_username} {fmt_range(s.start_time, s.end_time)} booked={s.is_booked}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def list_tutor_time_slots(self) -> None:
        tutor = prompt("Tutor username: ")
        try:
            resp = self.avail.ListTutorTimeSlots(avail_pb2.ListTutorTimeSlotsRequest(tutor_username=tutor))
            if not resp.check:
                print_header("Error")
                print(resp.message or "Request failed.")
                return
            print_header(f"Time Slots for {tutor}")
            if not resp.slot:
                print("(none)")
                return
            for s in resp.slot:
                print(f"[{s.id}] {fmt_range(s.start_time, s.end_time)} booked={s.is_booked}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def tutor_add_time_slot(self) -> None:
        if not self.session.token:
            print("Not logged in.")
            return

        print_header("Add Time Slot")
        print("Time Format: 2026-02-25 12:30 PM ")
        start_input = prompt("Start time: ")
        end_input = prompt("End time: ")

        try:
            start_time = to_iso(start_input)
            end_time = to_iso(end_input)
        except ValueError:
            print("Invalid datetime format.")
            print("Use: YYYY-MM-DD HH:MM AM/PM ")
            return

        req = avail_pb2.AddTimeSlotRequest(
            token=self.session.token,
            start_time=start_time,
            end_time=end_time,
        )
        try:
            resp = self.avail.AddTimeSlot(req)
            print(resp.message)
        except grpc.RpcError as e:
            show_rpc_error(e)

    def tutor_remove_time_slot(self) -> None:
        if not self.session.token:
            print("Not logged in.")
            return
        print_header("Remove Time Slot")
        slot_id = prompt_int("Slot ID to remove: ")

        req = avail_pb2.RemoveTimeSlotRequest(token=self.session.token, slot_id=slot_id)
        try:
            resp = self.avail.RemoveTimeSlot(req)
            print(resp.message)
        except grpc.RpcError as e:
            show_rpc_error(e)

    # -------------------------
    # Create Appointment (Student)
    # -------------------------
    def create_appointment(self) -> None:
        if not self.session.token:
            print("Not logged in.")
            return

        print_header("Create Appointment")
        slot_id = prompt_int("Slot ID to book: ")
        tutor_username = prompt("Tutor username (must match slot): ")

        req = create_pb2.CreateAppointmentRequest(
            token=self.session.token,
            slot_id=slot_id,
            tutor_username=tutor_username,
        )
        try:
            resp = self.create.CreateAppointment(req)
            print(resp.message)

            # Only print appointment fields on success
            if resp.appointment_id and (getattr(resp, "status", "") == "BOOKED" or resp.appointment_id != ""):
                print(
                    f"appointment_id={resp.appointment_id}\n"
                    f"student={resp.student_username} tutor={resp.tutor_username}\n"
                    f"{fmt_range(resp.start_time, resp.end_time)} status={resp.status}"
                )
        except grpc.RpcError as e:
            show_rpc_error(e)

    # -------------------------
    # Modify Appointment (Student)
    # -------------------------
    def get_appointment(self) -> None:
        print_header("Get Appointment")
        appointment_id = prompt("Appointment ID: ")
        try:
            resp = self.modify.GetAppointment(modify_pb2.GetAppointmentRequest(appointment_id=appointment_id))
            print(resp.message)

            if resp.appointment_id:
                print(
                    f"appointment_id={resp.appointment_id}\n"
                    f"student={resp.student_username} tutor={resp.tutor_username}\n"
                    f"{fmt_range(resp.start_time, resp.end_time)} status={resp.status}\n"
                    f"slot_id={getattr(resp, 'slot_id', 0)}"
                )
        except grpc.RpcError as e:
            show_rpc_error(e)

    def cancel_appointment(self) -> None:
        print_header("Cancel Appointment")
        appointment_id = prompt("Appointment ID: ")
        try:
            resp = self.modify.CancelAppointment(modify_pb2.CancelAppointmentRequest(token=self.session.token, appointment_id=appointment_id))
            print(resp.message)
            if resp.appointment_id:
                print(f"status={resp.status} appointment_id={resp.appointment_id}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def change_appointment(self) -> None:
        print_header("Change Appointment")
        appointment_id = prompt("Appointment ID: ")
        old_slot_id = prompt_int("Old slot ID: ")
        new_slot_id = prompt_int("New slot ID: ")

        req = modify_pb2.ChangeAppointmentRequest(
            token=self.session.token,
            appointment_id=appointment_id,
            old_slot_id=old_slot_id,
            new_slot_id=new_slot_id,
        )
        try:
            resp = self.modify.ChangeAppointment(req)
            print(resp.message)

            if getattr(resp, "status", "") == "CHANGED":
                print(
                    f"appointment_id={resp.appointment_id}\n"
                    f"student={resp.student_username} tutor={resp.tutor_username}\n"
                    f"{fmt_range(resp.start_time, resp.end_time)} status={resp.status}\n"
                    f"slot_id={getattr(resp, 'slot_id', 0)}"
                )
        except grpc.RpcError as e:
            show_rpc_error(e)

    # -------------------------
    # Rating (Student)
    # -------------------------
    def submit_rating(self) -> None:
        if not self.session.username:
            print("Missing student username in session (ValidateToken failed).")
            return

        print_header("Submit Rating")
        tutor_username = prompt("Tutor username to rate: ")
        rating_val = prompt_int("Rating (1-5): ")
        comment = prompt("Comment (optional): ")
        appointment_id = prompt("Appointment ID (optional, press enter to skip): ")

        timestamp_input = prompt(
            "Timestamp (optional, ex: 2026-02-25 12:30 PM or 2026-02-25T12:30:00, press enter to skip): "
        )

        if timestamp_input:
            try:
                timestamp = to_iso(timestamp_input)
            except ValueError:
                print("Invalid datetime format for timestamp.")
                print("Use: 2026-02-25 12:30 PM  OR  2026-02-25T12:30:00")
                return
        else:
            timestamp = ""

        req = rating_pb2.SubmitRatingRequest(
            student_username=self.session.username,
            tutor_username=tutor_username,
            appointment_id=appointment_id if appointment_id else "",
            rating=rating_val,
            comment=comment if comment else "",
            timestamp=timestamp,
        )
        try:
            resp = self.rating.SubmitRating(req)
            print(resp.message)
        except grpc.RpcError as e:
            show_rpc_error(e)

    def get_tutor_rating_summary(self) -> None:
        print_header("Tutor Rating Summary")
        tutor_username = prompt("Tutor username: ")
        try:
            resp = self.rating.GetTutorRatingSummary(rating_pb2.TutorRequest(tutor_username=tutor_username))
            print(resp.message)
            if resp.ok:
                print(f"{resp.tutor_username}: avg={resp.average_rating:.2f} (n={resp.rating_count})")
        except grpc.RpcError as e:
            show_rpc_error(e)

    def get_tutor_ratings(self) -> None:
        print_header("Tutor Ratings")
        tutor_username = prompt("Tutor username: ")
        try:
            resp = self.rating.GetTutorRatings(rating_pb2.TutorRequest(tutor_username=tutor_username))
            print(resp.message)
            if not resp.ok:
                return
            if not resp.items:
                print("(no ratings)")
                return
            for it in resp.items:
                print("-" * 40)
                print(f"student={it.student_username} rating={it.rating} time={it.timestamp}")
                if it.appointment_id:
                    print(f"appointment_id={it.appointment_id}")
                if it.comment:
                    print(f"comment: {it.comment}")
        except grpc.RpcError as e:
            show_rpc_error(e)

    # -------------------------
    # Menus
    # -------------------------
    def run(self) -> None:
        while True:
            choice = choose_menu(
                "Tutor Booking CLI",
                [
                    ("1", "Register as Student"),
                    ("2", "Register as Tutor"),
                    ("3", "Login"),
                    ("4", "Exit"),
                ],
            )

            if choice == "1":
                self.register_student()
            elif choice == "2":
                self.register_tutor()
            elif choice == "3":
                ok = self.login()
                if ok:
                    self.post_login_menu()
            elif choice == "4":
                print("Bye.")
                return

    def post_login_menu(self) -> None:
        role = self.session.role

        # NO_ROLE=0 STUDENT=1 TUTOR=2
        if role == auth_pb2.TUTOR:
            self.tutor_menu()
        elif role == auth_pb2.STUDENT:
            self.student_menu()
        else:
            print("Unknown role. Logging out for safety.")
            self.logout()

    def student_menu(self) -> None:
        while self.session.token:
            choice = choose_menu(
                f"Student Menu (logged in as {self.session.username or 'unknown'})",
                [
                    ("1", "List all tutors with time slots"),
                    ("2", "List all time slots"),
                    ("3", "List a tutor's time slots"),
                    ("4", "Create appointment"),
                    ("5", "Get appointment"),
                    ("6", "Cancel appointment"),
                    ("7", "Change appointment"),
                    ("8", "Submit rating (only needs tutor username)"),
                    ("9", "View tutor rating summary"),
                    ("10", "View tutor ratings (list)"),
                    ("0", "Logout"),
                ],
            )

            if choice == "1":
                self.list_all_tutors_with_slots()
            elif choice == "2":
                self.list_all_time_slots()
            elif choice == "3":
                self.list_tutor_time_slots()
            elif choice == "4":
                self.create_appointment()
            elif choice == "5":
                self.get_appointment()
            elif choice == "6":
                self.cancel_appointment()
            elif choice == "7":
                self.change_appointment()
            elif choice == "8":
                self.submit_rating()
            elif choice == "9":
                self.get_tutor_rating_summary()
            elif choice == "10":
                self.get_tutor_ratings()
            elif choice == "0":
                self.logout()
                return

    def tutor_menu(self) -> None:
        while self.session.token:
            choice = choose_menu(
                f"Tutor Menu (logged in as {self.session.username or 'unknown'})",
                [
                    ("1", "Add time slot"),
                    ("2", "Remove time slot"),
                    ("3", "List my time slots (by username)"),
                    ("4", "List all time slots"),
                    ("0", "Logout"),
                ],
            )

            if choice == "1":
                self.tutor_add_time_slot()
            elif choice == "2":
                self.tutor_remove_time_slot()
            elif choice == "3":
                tutor = self.session.username or ""
                if tutor:
                    print_header(f"Time Slots for {tutor}")
                    try:
                        resp = self.avail.ListTutorTimeSlots(avail_pb2.ListTutorTimeSlotsRequest(tutor_username=tutor))
                        if not resp.slot:
                            print("(none)")
                        else:
                            for s in resp.slot:
                                print(f"[{s.id}] {fmt_range(s.start_time, s.end_time)} booked={s.is_booked}")
                    except grpc.RpcError as e:
                        show_rpc_error(e)
                else:
                    self.list_tutor_time_slots()
            elif choice == "4":
                self.list_all_time_slots()
            elif choice == "0":
                self.logout()
                return


def main() -> None:
    try:
        Client().run()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()