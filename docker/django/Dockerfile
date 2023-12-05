FROM python:slim
ARG REQ_FILE
WORKDIR /
COPY $REQ_FILE requirements.txt

RUN pip3 install -r requirements.txt
RUN mkdir guard_bot
WORKDIR /guard_bot
ENTRYPOINT python
