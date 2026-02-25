import os
import grpc
import availability_pb2
import availability_pb2_grpc

ADDR = os.getenv("AVAIL_ADDR", "localhost:50052")

def main():
    with grpc.insecure_channel(ADDR) as channel:
        stub = availability_pb2_grpc.SetAvailabilityStub(channel)

        while True:
            print("Choose\n1) Add time slot\n2) Remove time slot\n3) List all tutors with slots\n4) List all time slots\n5) List specified tutor time slot\n6) Quit")
            c = input("Choose (1, 2, 3, 4, 5, or 6): ").strip()

            if c == "1":
                t = input("token: ")
                s = input("start_time (YYYY-MM-DDTHH:MM:SS): ")
                e = input("end_time (YYYY-MM-DDTHH:MM:SS): ")
                resp = stub.AddTimeSlot(availability_pb2.AddTimeSlotRequest(
                    token=t, start_time=s, end_time=e
                ))
                print(resp.check, resp.message)

            elif c == "2":
                t = input("token: ")
                slot_id = int(input("slot_id: "))
                resp = stub.RemoveTimeSlot(availability_pb2.RemoveTimeSlotRequest(
                    token=t, slot_id=slot_id
                ))
                print(resp.check, resp.message)

            elif c == "3":
                resp = stub.ListAllTutorsWithTimeSlots(
                    availability_pb2.Empty()
                )
                for t in resp.tutor_username:
                    print("-", t)

            elif c == "4": 
                resp = stub.ListAllTimeSlots(availability_pb2.Empty())
                for s in resp.slot:
                    print(f"- id={s.id} tutor_username={s.tutor_username} {s.start_time} -> {s.end_time} status={s.is_booked}")
            
            elif c == '5':
                tutor = input("tutor username: ")
                resp = stub.ListTutorTimeSlots(availability_pb2.ListTutorTimeSlotsRequest(tutor_username=tutor))
                for s in resp.slot:
                    print(f"- id={s.id} {s.start_time} -> {s.end_time} status={s.is_booked}")

            elif c == "6":
                break

if __name__ == "__main__":
    main()