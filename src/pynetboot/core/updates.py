"""Ask GitHub whether a newer release has been published.

Deliberately read-only and advisory: it reports what the latest release is
called and leaves downloading it to the user. Nothing here blocks the
application -- the caller runs it on a thread of its own -- and a check that
cannot be completed is not an error worth interrupting anyone over, so every
failure comes back as one "unknown" result rather than an exception.
"""
import logging
import re
from typing import NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

# The releases feed for this project. The API answers unauthenticated requests
# with a rate limit per address, which is ample for opening a dialog.
LATEST_RELEASE_API = ("https://api.github.com/repos/janos-szenfner/"
                      "unetbootin-python/releases/latest")
RELEASES_PAGE = ("https://github.com/janos-szenfner/unetbootin-python/"
                 "releases/latest")

# Short: this runs while a dialog sits there saying it is checking, and an
# unreachable network should resolve to "unknown" quickly rather than hang.
CHECK_TIMEOUT = 6

# Leading numeric components, so "v1.10.3" and "1.10.3-rc1" both compare.
_VERSION_RE = re.compile(r'^\D*(\d+(?:\.\d+)*)')


class UpdateCheck(NamedTuple):
    """What a check found. `latest` is set only when it is known."""

    status: str                     # 'current' | 'update' | 'unknown'
    latest: Optional[str] = None
    detail: str = ''

    @property
    def update_available(self) -> bool:
        return self.status == 'update'


def parse_version(text: Optional[str]) -> Optional[Tuple[int, ...]]:
    """Turn a release name into comparable numbers, or None if it is not one."""
    if not text:
        return None
    match = _VERSION_RE.match(text.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split('.'))


def is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    """True when `candidate` is a later version than `current`.

    Shorter numbers sort earlier at equal prefixes, so 1.10 precedes 1.10.1.
    Anything that does not parse is treated as not newer: a name nobody can
    order is no reason to tell someone they are out of date.
    """
    new, old = parse_version(candidate), parse_version(current)
    if new is None or old is None:
        return False
    length = max(len(new), len(old))
    return (new + (0,) * length)[:length] > (old + (0,) * length)[:length]


def latest_release(timeout: int = CHECK_TIMEOUT) -> Optional[str]:
    """The newest published release's tag, without its leading "v"."""
    import requests

    from pynetboot import APP_VERSION

    response = requests.get(
        LATEST_RELEASE_API, timeout=timeout,
        headers={'Accept': 'application/vnd.github+json',
                 'User-Agent': f'PyNetboot/{APP_VERSION}'})
    response.raise_for_status()
    tag = (response.json() or {}).get('tag_name')
    return tag.lstrip('vV') if tag else None


def check_for_update(current: Optional[str] = None,
                     timeout: int = CHECK_TIMEOUT) -> UpdateCheck:
    """Compare the newest release with what is running.

    Safe to call from a worker thread, and it never raises: a check that did
    not complete comes back as 'unknown', which the caller reports as such
    rather than as being up to date.
    """
    if current is None:
        from pynetboot import APP_VERSION
        current = APP_VERSION

    try:
        latest = latest_release(timeout)
    except Exception as e:  # noqa: BLE001 - any failure means "not known"
        logger.info(f"Update check did not complete: {e}")
        return UpdateCheck('unknown', detail=str(e))

    if latest is None:
        logger.info("Update check: no release name in the reply")
        return UpdateCheck('unknown', detail='no release name')

    if is_newer(latest, current):
        logger.info(f"Update check: {latest} is newer than {current}")
        return UpdateCheck('update', latest)

    logger.info(f"Update check: {current} is current (latest is {latest})")
    return UpdateCheck('current', latest)
