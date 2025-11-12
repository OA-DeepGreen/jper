FROM python:3.11

RUN apt-get update
RUN apt-get install git -y
WORKDIR /opt
RUN git clone http://github.com/OA-DeepGreen/store.git
WORKDIR /opt/store
RUN git fetch
RUN git pull origin master
RUN pip3 install --upgrade -e .
RUN pip3 install itsdangerous==2.0.1
RUN pip3 install Jinja2==3.0.3
RUN mkdir -p /home/green/jperstore
EXPOSE 5999
CMD ["python3", "/opt/store/store/app.py"]