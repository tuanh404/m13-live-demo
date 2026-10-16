"""One authenticated cookie session for a batch of read-only CVAT metadata requests."""

import os
from contextlib import contextmanager

import httpx


@contextmanager
def authenticated_client(url):
    user, password = os.environ.get("CVAT_USER"), os.environ.get("CVAT_PASSWORD")
    if not user or not password:
        raise ValueError("Thiếu credentials CVAT trong môi trường backend")
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        try:
            response = client.post(
                url.rstrip("/") + "/api/auth/login", json={"username": user, "password": password}
            )
            response.raise_for_status()
            if not client.cookies:
                raise ValueError("CVAT không tạo session đăng nhập")
        except httpx.HTTPError as exc:
            raise ValueError("Không đăng nhập được CVAT; kiểm backend credentials/kết nối") from exc
        yield client
