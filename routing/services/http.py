"""GET JSON from an external service (OSRM, Nominatim) within one total time limit.

`requests` applies its timeout to the connect and to each read separately, so a slow
trickle of data can keep a download going well past it. Here the download runs in a
worker thread, and the caller waits for it at most HTTP_TIMEOUT_SECONDS in total. The
worker also stops reading once that deadline has passed, so an abandoned download ends
soon after.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as WaitTimedOut
from time import monotonic

import requests
from django.conf import settings
from urllib3.exceptions import ReadTimeoutError

# The worker checks the deadline between chunks; small chunks notice a trickling body
# early (OSRM has sent ~150 KB over 37 s).
CHUNK_BYTES = 4 * 1024
_workers = ThreadPoolExecutor(max_workers=16, thread_name_prefix="http")


class DeadlinePassed(requests.Timeout):
    """The whole answer did not arrive within the time limit."""


def get_json(url: str, params: dict, headers: dict | None = None) -> tuple[int, object]:
    """GET `url`; return the HTTP status and the JSON body.

    Raises requests.Timeout if the complete answer takes longer than HTTP_TIMEOUT_SECONDS,
    another requests.RequestException if the service can't be reached, and ValueError if
    the body is not JSON.
    """
    limit = settings.HTTP_TIMEOUT_SECONDS
    deadline = monotonic() + limit
    download = _workers.submit(_download, url, params, headers, limit, deadline)
    try:
        status, content = download.result(timeout=limit)
    except WaitTimedOut as error:
        raise DeadlinePassed(f"No complete answer within {limit:g} s.") from error
    return status, json.loads(content)


def _download(
    url: str, params: dict, headers: dict | None, limit: float, deadline: float
) -> tuple[int, bytes]:
    try:
        with requests.get(
            url, params=params, headers=headers, timeout=limit, stream=True
        ) as response:
            chunks = []
            for chunk in response.iter_content(CHUNK_BYTES):
                if monotonic() > deadline:
                    raise DeadlinePassed(f"No complete answer within {limit:g} s.")
                chunks.append(chunk)
            return response.status_code, b"".join(chunks)
    except requests.ConnectionError as error:
        # requests reports a read that times out in the middle of the body as a ConnectionError
        if error.args and isinstance(error.args[0], ReadTimeoutError):
            raise requests.ReadTimeout(str(error)) from error
        raise
