FROM python:3.12-alpine
RUN apk add --no-cache tzdata         && cp /usr/share/zoneinfo/America/Los_Angeles /etc/localtime         && echo 'America/Los_Angeles' > /etc/timezone
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY twitch_vod_downloader.py /app/twitch_vod_downloader.py
CMD ["python", "/app/twitch_vod_downloader.py"]
