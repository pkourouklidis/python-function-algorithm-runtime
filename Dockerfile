FROM python:3.10-alpine

#install packages
RUN apk add --no-cache git

# Install python packages
COPY requirements.txt /app/requirements.txt
RUN pip --disable-pip-version-check --no-cache-dir install -r /app/requirements.txt

# Copy source files
COPY app.py /app/
COPY project /app/project
COPY template /app/template
COPY HOtemplate /app/HOtemplate
WORKDIR /app

# Start application
ENV FLASK_APP=/app/app.py
CMD [ "flask", "run", "--host=0.0.0.0"]