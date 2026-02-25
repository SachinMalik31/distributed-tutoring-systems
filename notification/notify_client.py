import grpc
import notification_pb2
import notification_pb2_grpc


ADDR = "localhost:50053"


def test_booking_email(stub):
    print("\n=== Testing Booking Confirmation ===")

    response = stub.SendBookingConfirmation(
        notification_pb2.SendBookingConfirmationRequest(
            user_email="student@example.com", 
            tutor_email="tutor@example.com",
            user_username="student1",
            tutor_username="tutor1",
            start_time="2026-02-20T15:00:00",
            end_time="2026-02-20T16:00:00",
            appointment_id="APPT123"
        )
    )

    print("Response:", response.check, response.message)


def test_cancellation_email(stub):
    print("\n=== Testing Cancellation Notice ===")

    response = stub.SendCancellationNotice(
        notification_pb2.SendCancellationNoticeRequest(
            user_email="student@example.com",
            tutor_email="tutor@example.com",
            user_username="student1",
            tutor_username="tutor1",
            start_time="2026-02-20T15:00:00",
            end_time="2026-02-20T16:00:00",
            appointment_id="APPT123",
            cancelled_by="student",
        )
    )

    print("Response:", response.check, response.message)


def main():
    with grpc.insecure_channel(ADDR) as channel:
        stub = notification_pb2_grpc.NotifierStub(channel)

        test_booking_email(stub)
        test_cancellation_email(stub)


if __name__ == "__main__":
    main()