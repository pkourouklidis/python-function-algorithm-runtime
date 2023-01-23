FROM python:3.10

# Install python packages
COPY requirements.txt /app/requirements.txt
RUN pip --disable-pip-version-check --no-cache-dir install -r /app/requirements.txt

# Copy source files
COPY main.py /app/
COPY feature_store.yaml /app/
COPY detector.py /app/
WORKDIR /app

# Start application
CMD [ "python", "main.py"]