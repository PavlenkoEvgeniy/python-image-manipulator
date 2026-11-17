"""Optional check for a newer GitHub release at every startup.

The module is pure Python and Tk-free: the UI runs it in a worker thread and
opens the chosen download URL through the operating system's default browser.
Network access happens only when ``check_for_update()`` is called, never at
import time.
"""

import json
import logging
import re
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from . import __version__

logger = logging.getLogger(__name__)

REPOSITORY = "PavlenkoEvgeniy/python-image-manipulator"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"

REQUEST_TIMEOUT_SECONDS = 6
MAX_RESPONSE_BYTES = 1_000_000

_VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)*)")

_DEB_DISTROS = {
    "debian",
    "ubuntu",
    "linuxmint",
    "pop",
    "elementary",
    "zorin",
}
_RPM_DISTROS = {
    "fedora",
    "rhel",
    "centos",
    "rocky",
    "almalinux",
    "opensuse",
    "opensuse-leap",
    "opensuse-tumbleweed",
    "suse",
    "amzn",
}


@dataclass(frozen=True)
class UpdateInfo:
    """A newer release and the download link for the current platform."""

    version: str
    download_url: str
    release_url: str


def parse_version(text: str) -> Optional[tuple[int, ...]]:
    """Extract the first dotted numeric version from a tag or version string."""
    match = _VERSION_PATTERN.search(text or "")
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str = __version__) -> bool:
    """Return True when ``candidate`` is a strictly newer numeric version."""
    newer = parse_version(candidate)
    current_version = parse_version(current)
    if newer is None or current_version is None:
        return False
    return newer > current_version


def platform_asset_key(platform: Optional[str] = None) -> str:
    """Map a ``sys.platform`` value to the release asset name fragment."""
    value = sys.platform if platform is None else platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    return "linux"


def linux_package_kind(
    os_release: str = "/etc/os-release",
    which=shutil.which,
) -> str:
    """Return ``deb`` or ``rpm`` for the running Linux distribution."""
    identifiers = set()
    try:
        with open(os_release, encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition("=")
                if key in ("ID", "ID_LIKE"):
                    identifiers.update(value.strip().strip('"').lower().split())
    except OSError:
        pass

    if identifiers & _DEB_DISTROS:
        return "deb"
    if identifiers & _RPM_DISTROS:
        return "rpm"
    if which("apt-get") or which("dpkg"):
        return "deb"
    if which("dnf") or which("yum") or which("zypper") or which("rpm"):
        return "rpm"
    return "deb"


def _https_assets(assets: Any, key: str) -> list:
    """Assets whose name matches the platform and whose URL is https."""
    matches = []
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "")).lower()
            url = asset.get("browser_download_url")
            if key in name and isinstance(url, str) and url.startswith("https://"):
                matches.append((name, url))
    return matches


def pick_download_url(
    assets: Any,
    platform: Optional[str] = None,
    release_url: str = RELEASES_PAGE,
    package_kind: Optional[str] = None,
) -> str:
    """Pick the direct installer URL for the platform.

    Linux prefers the package type of the running distribution; macOS and
    Windows prefer disk-image and setup installers. Falls back to the release
    page when no suitable asset exists.
    """
    key = platform_asset_key(platform)
    matches = _https_assets(assets, key)
    if not matches:
        return release_url

    if key == "linux":
        kind = package_kind or linux_package_kind()
        for suffix in ("." + kind, ".deb", ".rpm", ".appimage"):
            for name, url in matches:
                if name.endswith(suffix):
                    return url
    elif key == "windows":
        for name, url in matches:
            if "setup" in name or name.endswith(".msi"):
                return url
    elif key == "macos":
        for name, url in matches:
            if name.endswith((".dmg", ".pkg")):
                return url

    return matches[0][1]


def parse_latest_release(
    payload: Any,
    platform: Optional[str] = None,
    current_version: str = __version__,
    package_kind: Optional[str] = None,
) -> Optional[UpdateInfo]:
    """Turn a GitHub ``releases/latest`` payload into UpdateInfo.

    Returns None when the payload is malformed or the release is not newer.
    """
    if not isinstance(payload, dict):
        return None

    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not is_newer(tag, current_version):
        return None

    match = _VERSION_PATTERN.search(tag)
    version = match.group(1) if match is not None else tag.lstrip("vV")

    release_url = payload.get("html_url")
    if not isinstance(release_url, str) or not release_url.startswith("https://"):
        release_url = RELEASES_PAGE

    return UpdateInfo(
        version=version,
        download_url=pick_download_url(
            payload.get("assets"),
            platform=platform,
            release_url=release_url,
            package_kind=package_kind,
        ),
        release_url=release_url,
    )


def fetch_latest_release(timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Fetch the latest release metadata from the GitHub API.

    Raises:
        OSError: on network or HTTP errors.
        ValueError: when the response is not a JSON object.
    """
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ImageManipulator/{__version__}",
        },
    )
    with urllib.request.urlopen(  # noqa: S310 - constant https URL
        request, timeout=timeout
    ) as response:
        body = response.read(MAX_RESPONSE_BYTES)

    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("the release payload is not an object")
    return payload


def check_for_update(
    platform: Optional[str] = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> Optional[UpdateInfo]:
    """Run one network check and return update information when available."""
    payload = fetch_latest_release(timeout=timeout)
    return parse_latest_release(payload, platform=platform)
