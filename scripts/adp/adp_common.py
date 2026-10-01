"""Shared ADP client for the scratch scripts (key read from RydeResolve's .env, never printed)."""
from pathlib import Path

from dotenv import dotenv_values
from tencentcloud.common import credential
from tencentcloud.lke.v20231130 import lke_client, models  # noqa: F401  (re-exported)

ENV = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
CRED = credential.Credential(ENV["TENCENTCLOUD_SECRET_ID"].strip(), ENV["TENCENTCLOUD_SECRET_KEY"].strip())
REGION = (ENV.get("TENCENTCLOUD_REGION") or "ap-jakarta").strip()
client = lke_client.LkeClient(CRED, REGION)


def the_app():
    req = models.ListAppRequest()
    req.PageNumber, req.PageSize = 1, 20
    apps = client.ListApp(req).List or []
    if len(apps) != 1:
        raise SystemExit(f"expected exactly 1 ADP app, found {len(apps)}")
    return apps[0]
