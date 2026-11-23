# One image per commit, the same in every environment.
#   default command: the hub (dashboard + API) on port 8000, one process (state lives in memory)
#   one-off jobs run by the pipeline with another command:
#     python -m milk.selfcheck   end-to-end check of a deployed hub (test environment)
#     python -m milk.reindex     rebuild the captures table from the result files in S3
# The counting worker (GPU, ffmpeg) and MediaMTX are not in this image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/server

# Take the distribution's security fixes so the image scan finds nothing fixable.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
# pip and setuptools are only needed to install; remove them so the running image does not
# carry them. (pip vendors part of setuptools 70.3.0, which the image scan flags as
# CVE-2025-47273 through pip/_vendor/bom.cdx.json.)
RUN pip install -r server/requirements.txt \
 && (pip uninstall -y setuptools wheel || true) \
 && python -m pip uninstall -y pip \
 && python -c "import fastapi, uvicorn, boto3, numpy"

COPY server/milk server/milk
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin milk
USER 10001

EXPOSE 8000
CMD ["uvicorn", "milk.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "20"]
