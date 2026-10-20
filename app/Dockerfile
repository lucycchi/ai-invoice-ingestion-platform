FROM python:3.13-slim

WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY . /srv/app
ENV PYTHONPATH=/srv
EXPOSE 8080
CMD ["python", "-m", "app"]
