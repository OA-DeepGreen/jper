FROM python:3.11


RUN apt-get update
RUN apt-get install curl git sudo -y

COPY . /opt/jper
WORKDIR /opt/jper
RUN pip3 install --upgrade -r requirements.txt
RUN pip3 install itsdangerous==2.0.1
RUN pip3 install WTForms==2.3.3
RUN mkdir -p /home/sftpusers
RUN mkdir -p /home/green