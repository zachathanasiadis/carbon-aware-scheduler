FROM python:3.13-slim

WORKDIR /src

RUN pip install kopf kubernetes requests pyyaml 

COPY scheduler.py workload.yaml .

CMD ["kopf", "run", "scheduler.py"]
