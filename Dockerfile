FROM public.ecr.aws/lambda/python:3.12

# Static ffmpeg binary (Amazon Linux 2023 doesn't have ffmpeg in default repos)
RUN dnf install -y tar xz && \
    curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | \
    tar xJ --strip-components=1 -C /usr/local/bin/ --wildcards '*/ffmpeg' && \
    dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt yt-dlp==2026.3.13

COPY anygif.sh /usr/local/bin/anygif
RUN chmod +x /usr/local/bin/anygif

COPY app/ ${LAMBDA_TASK_ROOT}/app/

CMD ["app.lambda_webhook.handler"]
