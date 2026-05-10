FROM python:3.13-alpine

RUN apk add --no-cache ffmpeg

WORKDIR /app

COPY pyproject.toml .
RUN python -c "import tomllib; f=open('pyproject.toml','rb'); print('\n'.join(tomllib.load(f)['project']['dependencies']))" | xargs pip install --no-cache-dir

COPY . .
RUN pip install --no-cache-dir --no-deps .

ENV TIDDL_PATH=/data/tiddl

WORKDIR /data

ENTRYPOINT ["tiddl"]
