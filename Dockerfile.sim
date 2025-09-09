# Small, fast container
FROM python:3.11-slim

WORKDIR /app
# Only need the simulator and requests
COPY wgc_sim.py /app/
RUN pip install --no-cache-dir requests

# Defaults (can be overridden by env on the job)
ENV TWIN_URL="" \
    SIM_HZ=1.0 \
    SIM_VERBOSE=1 \
    SIM_LOG_EVERY=60

CMD ["python", "/app/wgc_sim.py"]

