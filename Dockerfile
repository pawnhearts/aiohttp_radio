FROM python:3.9.0-buster
#RUN apt-get update && apk add gcc python3-dev musl-dev libffi-dev make bind-tools 
#RUN apt-get update
#RUN apt-get install -y python3-mpd python3-aiohttp
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY web /web
WORKDIR /web
EXPOSE 8888
CMD python server.py
