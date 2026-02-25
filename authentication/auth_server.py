from concurrent import futures
import logging
import sys
import os 
import sqlite3
import uuid
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import authentication_pb2
import authentication_pb2_grpc

DB_PATH = os.getenv("DB_PATH", "users.db")
TUTOR_CODE = os.getenv('TUTOR_CODE', 'tutor1234')

def db_connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firstname TEXT NOT NULL,
            lastname TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('STUDENT','TUTOR'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    return conn

def role_to_str(role):
    if role == authentication_pb2.TUTOR:
        return 'TUTOR'
    else:
        return 'STUDENT'
    

def str_to_role(string):
    if string == 'TUTOR':
        return authentication_pb2.TUTOR
    else:
        return authentication_pb2.STUDENT

class Authenticator(authentication_pb2_grpc.AuthenticatorServicer):
    def __init__(self):
        self.conn = db_connect()
        self.conn.row_factory = sqlite3.Row

    def _validate_input(self, request):
        for field_name in ['firstname', 'lastname', 'username', 'email', 'password']:
            if not getattr(request, field_name).strip():
                return False, f"{field_name} is required\n"
            
        if request.role not in (authentication_pb2.STUDENT, authentication_pb2.TUTOR):
            return False, f"Role must be STUDENT or TUTOR\n"
        
        if request.role == authentication_pb2.TUTOR:
            if request.tutor_code != TUTOR_CODE:
                return False, f"Incorrect Tutor Code\n"
        return True, f"Inputs are valid\n"

    def _create_user(self, firstname: str, lastname: str,username: str, email: str, password: str, role: str):
        try:
            cur = self.conn.execute(
                'INSERT INTO users (firstname, lastname, username, email, password, role) VALUES (?,?,?,?,?,?)',
                (firstname.strip(), lastname.strip(), username.strip(), email.strip().lower(), password, role,)
            )
            self.conn.commit()
            user_id = cur.lastrowid
        except sqlite3.IntegrityError as e:
            msg = str(e).lower()
            if 'users.username' in msg:
                return False, f'Username already exists\n'
            if 'users.email' in msg:
                return False, f'Email already exists\n'
            return False, f'User already exists\n'
        
        return True, f'User registered as: {role}'

    
    def RegisterUser(self, request, context):
        flag, msg = self._validate_input(request)
        if flag is not True:
            return authentication_pb2.AuthenticatorReply(check=flag, message=msg)
        else:
            role_str = role_to_str(request.role)
            check, message  = self._create_user(request.firstname, request.lastname, request.username, request.email, request.password, role_str)
            return authentication_pb2.AuthenticatorReply(check=check, message=message, token='', role=request.role)


    def Login(self, request, context):
        user_login = request.username_or_email.strip()
        cursor = self.conn.execute(
            'SELECT id, username, email, password, role FROM users WHERE username = ? OR email = ?',
            (user_login, user_login.lower(),),
        )
        row = cursor.fetchone()
        if row is None:
            return authentication_pb2.AuthenticatorReply(check=False, message='User not found\n')
        if request.password != row['password']:
            return authentication_pb2.AuthenticatorReply(check=False, message='Password is incorrect\n')
        
        token = str(uuid.uuid4())
        self.conn.execute(
            'INSERT INTO tokens (token, user_id) VALUES (?,?)',
            (token, row['id'],) ,
        )
        self.conn.commit()
        role = str_to_role(row['role'])
        return authentication_pb2.AuthenticatorReply(check=True, message=f"Login successful: {row['role']}", token=token, role=role)
    


    def ValidateToken(self, request, context):
        token = request.token.strip()
        if token is None:
            return authentication_pb2.ValidateTokenReply(check=False, message='Token required\n')
        
        cursor = self.conn.execute(
            'SELECT t.token, u.firstname, u.lastname, u.username, u.email, u.role FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.token = ?',
            (token,),
        )

        row = cursor.fetchone()
        if row is None:
            return authentication_pb2.ValidateTokenReply(check=False, message='Token not found\n')
        else:
            return authentication_pb2.ValidateTokenReply(check=True, message='Token found for:', firstname=row['firstname'], lastname=row['lastname'], username=row['username'], email=row['email'], role=row['role'])
        


    def Logout(self, request, context):
        token = request.token.strip()
        if token is None:
            return authentication_pb2.LogoutReply(check=False, message='Token required\n')
        
        cursor = self.conn.execute(
            'DELETE FROM tokens WHERE token = ?',
            (token,),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            return authentication_pb2.LogoutReply(check=False, message='Token not found\n')
        else:
            return authentication_pb2.LogoutReply(check=False, message='Logged Out\n')
        
    
    def ListAllUsers(self, request, context):
        cursor = self.conn.execute(
            'SELECT firstname, lastname, username, email, role FROM users ORDER BY lastname'
        )
        users = [
            authentication_pb2.UserInfo(firstname=row['firstname'], lastname=row['lastname'], username=row['username'], email=row['email'], role=row['role'])
            for row in cursor.fetchall()
            ]
        return authentication_pb2.ListAllUsersReply(user=users)
    
    def GetUser(self, request, context):
        cursor = self.conn.execute(
            'SELECT firstname, lastname, email, role FROM users WHERE username = ?',
            (request.username,),
        )
        row = cursor.fetchone()
        if row is None:
            return authentication_pb2.GetUserReply(check=False, message='User not found')
        return authentication_pb2.GetUserReply(check=True, message='', firstname=row['firstname'], lastname=row['lastname'], email=row['email'], role=row['role'])


def serve():
    port = "50051"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    authentication_pb2_grpc.add_AuthenticatorServicer_to_server(Authenticator(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("Authenticator Service started, listening on " + port,flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    serve()