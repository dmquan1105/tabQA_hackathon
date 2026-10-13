FROM python:3.12.8-slim

WORKDIR /solution
COPY . /solution
RUN sed -i 's/\r$//' /solution/run.sh && chmod +x /solution/run.sh

ENTRYPOINT ["/solution/run.sh"]
