FROM python:3.7

EXPOSE 8080

RUN apt-get update && apt-get install zip unzip -qy && mkdir /app
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY . /app

ENTRYPOINT ["python","server.py"]