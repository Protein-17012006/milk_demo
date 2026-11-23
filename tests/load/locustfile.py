"""Load test of the hub, run by scripts/ci/load_test.sh during staging and production deployments.

Each simulated user logs in (LOCUST_WEB_PASSWORD, read from the environment's secret by the
pipeline) and then loads what the dashboard loads. /api/live is left out on purpose: it
long-polls for up to 20 s by design, which would hide real slowness in the p95.

    locust -f tests/load/locustfile.py --headless -u 20 -r 5 --run-time 5m --host http://<alb>:8080
"""

import os

from locust import HttpUser, between, task


class DashboardUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        password = os.environ.get("LOCUST_WEB_PASSWORD")
        if password:
            self.client.post("/api/login", json={"password": password}, name="/api/login")

    @task(3)
    def dashboard(self) -> None:
        self.client.get("/", name="/")

    @task(2)
    def history(self) -> None:
        self.client.get("/api/history?minutes=10", name="/api/history")

    @task(2)
    def skus_and_flags(self) -> None:
        self.client.get("/api/skus", name="/api/skus")
        self.client.get("/api/flags?limit=50", name="/api/flags")

    @task(1)
    def static_files(self) -> None:
        self.client.get("/static/app.js", name="/static/app.js")
        self.client.get("/static/style.css", name="/static/style.css")

    @task(1)
    def health(self) -> None:
        self.client.get("/healthz", name="/healthz")
