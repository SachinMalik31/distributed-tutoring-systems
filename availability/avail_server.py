from concurrent import futures
from datetime import datetime
import logging
import sys
import os 
import sqlite3
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import authentication_pb2
import authentication_pb2_grpc
import availability_pb2
import availability_pb2_grpc



DB_PATH = os.getenv("AVAIL_DB_PATH", "slots.db")
AUTH_ADDR = os.getenv("AUTH_ADDR", "auth:50051")

def db_connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutor_username TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_booked TEXT NOT NULL
        )
    ''')
#INTEGER NOT NULL DEFAULT 0
    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_slot ON slots(tutor_username, start_time, end_time)
    ''')
    conn.commit()
    return conn

# def int_to_str(val):
#     if val == 1:
#         return 'Booked'
#     else:
#         return 'Not Booked'
    
def str_to_date(val):
    return datetime.fromisoformat(val)

class Availability(availability_pb2_grpc.SetAvailabilityServicer):
    def __init__(self):
        self.conn = db_connect()
        self.auth_channel = grpc.insecure_channel(AUTH_ADDR)
        self.auth_stub = authentication_pb2_grpc.AuthenticatorStub(self.auth_channel) 


    def _verify_tutor(self, token: str):
        try:
            resp = self.auth_stub.ValidateToken(authentication_pb2.ValidateTokenRequest(token=token))
        except:
            return None, f'Unable to access Authentication Server.\n'
        
        if resp.role != authentication_pb2.TUTOR:
            return None, f'You are not a tutor\n'
        if resp.check is not True:
            return None, resp.message
        return resp.username, None
    


    def AddTimeSlot(self, request, context):
        tutor_username, err = self._verify_tutor(request.token)
        if err is not None:
            return availability_pb2.SlotAvailabilityReply(check=False, message=err)
        
        start_time = request.start_time.strip()
        end_time = request.end_time.strip()
        
        if start_time == '' or end_time == '':
            return availability_pb2.SlotAvailabilityReply(check=False, message='Start/End times can not be empty\n')
        

        try:
            start_dt = str_to_date(start_time)
            end_dt = str_to_date(end_time)
        except:
            return availability_pb2.SlotAvailabilityReply(check=False, message='Invalid format. Use ISO like 2026-02-12T12:00:00\n')

        if end_dt <= start_dt:
             return availability_pb2.SlotAvailabilityReply(check=False, message='End time must be after Start time\n')
        
        try:
            self.conn.execute('BEGIN IMMEDIATE')
            cursor = self.conn.execute(
                'SELECT 1 FROM slots WHERE tutor_username = ? AND is_booked = "NOT BOOKED" AND (? < end_time) AND (? > start_time) LIMIT 1',
                (tutor_username, start_time, end_time)
            )
            overlap = cursor.fetchone()

            if overlap is not None:
                self.conn.rollback()
                return availability_pb2.SlotAvailabilityReply(check=False, message="Time slot overlaps an existing slot")
            

            self.conn.execute(
                'INSERT INTO slots (tutor_username, start_time, end_time, is_booked) VALUES (?, ?, ?, ?)',
                (tutor_username, start_time, end_time, "NOT BOOKED")
            )

            self.conn.commit()
        except:
            return availability_pb2.SlotAvailabilityReply(check=False, message='Could not add time slot\n')
        return availability_pb2.SlotAvailabilityReply(check=True, message='Time slot added successfully!\n')
    


    def RemoveTimeSlot(self, request, context):
        tutor_username, err = self._verify_tutor(request.token)
        if err is not None:
            return availability_pb2.SlotAvailabilityReply(check=False, message=err)
        
        slot_id = int(request.slot_id)
        
        cursor = self.conn.execute(
            'SELECT id, tutor_username, is_booked FROM slots WHERE id = ?',
            (slot_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return availability_pb2.SlotAvailabilityReply(check=False, message='Slot not found\n')
        
        if row[1] != tutor_username:
            return availability_pb2.SlotAvailabilityReply(check=False, message="Cannot remove another tutor's time slot")
        
        if row[2] == "BOOKED":
            return availability_pb2.SlotAvailabilityReply(check=False, message="Cannot remove booked time slot")

        self.conn.execute(
            'DELETE FROM slots WHERE id = ?',
            (slot_id,),
        )

        self.conn.commit()
        return availability_pb2.SlotAvailabilityReply(check=True, message='Time slot removed successfully!\n')
    

    def ListAllTutorsWithTimeSlots(self, request, context):
        cursor = self.conn.execute(
            'SELECT DISTINCT tutor_username FROM slots ORDER BY tutor_username'
        )
        tutor_username = [row[0] for row in cursor.fetchall()]
        return availability_pb2.ListAllTutorsWithTimeSlotsReply(tutor_username=tutor_username)
    

    def ListAllTimeSlots(self, request, context):
        cursor = self.conn.execute(
            'SELECT id, tutor_username, start_time, end_time, is_booked FROM slots ORDER BY start_time, tutor_username'
        )
        slot = [
            availability_pb2.Slots(id=row[0], tutor_username=row[1], start_time=row[2], end_time=row[3], is_booked= row[4])
            for row in cursor.fetchall()
        ]
        return availability_pb2.ListTimeSlotsReply(slot=slot)


    def ListTutorTimeSlots(self, request, context):
        resp_tutor = self.auth_stub.GetUser(authentication_pb2.GetUserRequest(username=request.tutor_username))

        if resp_tutor.check == False:
            return availability_pb2.ListTimeSlotsReply(check=False, message="Tutor username does not exist")
        
        if resp_tutor.role != authentication_pb2.TUTOR:
            return availability_pb2.ListTimeSlotsReply(check=False, message="Name entered is not a tutor")

        cursor = self.conn.execute(
            'SELECT id, tutor_username, start_time, end_time, is_booked FROM slots WHERE tutor_username = ? ORDER BY start_time',
            (request.tutor_username,),
        )
        slots = [
            availability_pb2.Slots(id=row[0], tutor_username=row[1], start_time=row[2], end_time=row[3], is_booked= row[4])
            for row in cursor.fetchall()
        ]
        return availability_pb2.ListTimeSlotsReply(check=True, slot=slots)
    
    def UpdateTimeSlotStatus(self, request, context):
        if request.is_booked == 'BOOKED':
            cursor = self.conn.execute(
                'UPDATE slots SET is_booked = "BOOKED" WHERE id = ? AND is_booked = "NOT BOOKED"',
                (request.new_slot_id,),
            )
            if cursor.rowcount == 0:
                return availability_pb2.UpdateTimeSlotStatusReply(check=False, message='Time slot already booked')     
        elif request.is_booked == "CANCELED":
            cursor = self.conn.execute(
                'UPDATE slots SET is_booked = "NOT BOOKED" WHERE id = ? AND is_booked = "BOOKED"',
                (request.new_slot_id,),
            )
            if cursor.rowcount == 0:
                return availability_pb2.UpdateTimeSlotStatusReply(check=False, message='Time slot already not booked')
        else:
            if request.is_booked == "CHANGED":
                try:
                    self.conn.execute('BEGIN IMMEDIATE')
                    cursor1 = self.conn.execute(
                        'UPDATE slots SET is_booked = "NOT BOOKED" WHERE id = ? AND is_booked = "BOOKED"',
                        (request.old_slot_id,),
                    )
                    if cursor1.rowcount != 1:
                        self.conn.execute("ROLLBACK")
                        return availability_pb2.UpdateTimeSlotStatusReply(check=False, message="Old slot not booked")
                    
                    cursor2 = self.conn.execute(
                        'UPDATE slots SET is_booked = "BOOKED" WHERE id = ? AND is_booked = "NOT BOOKED"',
                        (request.new_slot_id,),
                    )
                    if cursor2.rowcount != 1:
                        self.conn.execute("ROLLBACK")
                        return availability_pb2.UpdateTimeSlotStatusReply(check=False, message="New slot already booked")
                except:
                    self.conn.execute('ROLLBACK')
                    return availability_pb2.UpdateTimeSlotStatusReply(check=False, message='Could not change time slot')

        self.conn.commit()        
        return availability_pb2.UpdateTimeSlotStatusReply(check=True, message='Time slot status updated')
    
    
    def GetSlot(self, request, context):
        cursor = self.conn.execute(
            'SELECT id, tutor_username, start_time, end_time, is_booked FROM slots WHERE id = ?',
            (request.slot_id,),
        ) 
        row = cursor.fetchone()
        if row is None:
            return availability_pb2.GetSlotReply(check=False, message="Time slot does not exist")
        slot = availability_pb2.Slots(id=row[0], tutor_username=row[1], start_time=row[2], end_time=row[3], is_booked= row[4])
        return availability_pb2.GetSlotReply(check=True, message="", slot=slot)


def serve():
    port = "50052"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    availability_pb2_grpc.add_SetAvailabilityServicer_to_server(Availability(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("Availability Service started, listening on " + port,flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    serve()