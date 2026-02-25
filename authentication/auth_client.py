import os
import grpc
import authentication_pb2
import authentication_pb2_grpc

def run():
    target = os.getenv("SERVER_ADDR", "localhost:50051")

    with grpc.insecure_channel(target) as channel:
        stub = authentication_pb2_grpc.AuthenticatorStub(channel)

        while True:
            print('Choose one of the following:\n1) Register Student\n2) Register Tutor\n3) Login\n4) Validate Token\n5) View all users\n6) Logout\n7) Quit')
            choice = input('Choose (1, 2, 3, 4, 5, 6, or 7): '.strip())

            if choice == '1':
                firstname = input('first name: ')
                lastname = input('last name: ')
                username = input('username: ')
                email = input('email: ')
                password = input('password: ')
                role = authentication_pb2.STUDENT
                response = stub.RegisterUser(authentication_pb2.RegisterUserRequest(firstname=firstname, lastname=lastname, username=username, email=email, password=password, role=role))
                print(response.message)
            elif choice == '2':
                firstname = input('first name: ')
                lastname = input('last name: ')
                username = input('username: ')
                email = input('email: ')
                password = input('password: ')
                role = authentication_pb2.TUTOR
                tutor_code = input('tutor code: ')
                response = stub.RegisterUser(authentication_pb2.RegisterUserRequest(firstname=firstname, lastname=lastname, username=username, email=email, password=password, role=role, tutor_code=tutor_code))
                print(response.message)
            elif choice == '3':
                userlogin = input('username or email: ')
                password = input('password: ')
                response = stub.Login(authentication_pb2.LoginRequest(username_or_email=userlogin, password=password))
                print(response.message, response.token)
            elif choice == '4':
                token = input('token: ')
                response = stub.ValidateToken(authentication_pb2.ValidateTokenRequest(token=token))
                print(response)
            elif choice == '5':
                response = stub.ListAllUsers(authentication_pb2.Empty())
                for u in response.user:
                    print(u)
            elif choice == '6':
                token = input('token: ')
                response = stub.Logout(authentication_pb2.LogoutRequest(token=token))
                print(response.message)
            elif choice == '7':
                break
            else: 
                print('Invalid choice')

if __name__ == "__main__":
    run()
