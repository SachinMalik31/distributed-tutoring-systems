**Distributed Tutoring System**

This project implements a distributed tutoring system supporting the following functionalities:

1. User login system

2. Book appointments

3. Modify/cancel appointments

4. Tutors set availability

5. Email notifications

6. Tutor rating system




**System Requirements**

Python 3.9+

Docker 

pip package manager


**Tested on**

Windows 11

Intel i7 CPU


**Installation**

1. For installing python, follow this website: https://www.python.org/downloads/. TO check python version use the following code snippet and ensure your version is at least 3.11
    
    python --version
   
For pip, it should already be installed with python. Use following code snippet to check pip version and ensure it is at least 9.0.1
    pip --version
   
If pip version is too old, run following command
    
    python -m pip install --upgrade pip
   
For gRPC, use following command to install
    
    python -m pip install grpcio
    
To install gRPC tools for python, run the following command
    
    python -m pip install grpcio-tools
    

2. Clone the Repository
     git clone 
     cd 

3. Create Virtual Environment ( Optional )
    python -m venv venv
    venv\Scripts\activate   # Windows


**Running the System**

1. Docker Deployment

   Build containers:   docker-compose build

   Start services:   docker-compose up

*Run CLI after containers are active*

2. CLI Executio(main_client folder):
     
    python client.py

will see a menu for login,register etc.,


**Authors**

Peter Nguyen
UTA Student ID: 1002366598
pxn6598@mavs.uta.edu

Sachin Malik
UTA Student ID: 1002202264
sxm2264@mavs.uta.edu

**Version History**

* 0.1
    * Initial Release


**Acknowledgments**

External references
* ChatGPT
