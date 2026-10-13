FROM python:3.12.8-slim

WORKDIR /app
COPY . .
RUN sed -i 's/\r$//' run.sh && chmod +x run.sh

ENTRYPOINT ["./run.sh"]
