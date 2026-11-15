"""Tests for the optional GitHub update check."""

import pytest

from image_manipulator import update_checker

ASSETS = [
    {
        "name": "ImageManipulator-9.0.0-linux-amd64.deb",
        "browser_download_url": "https://example.com/linux.deb",
    },
    {
        "name": "ImageManipulator-9.0.0-linux-x86_64.rpm",
        "browser_download_url": "https://example.com/linux.rpm",
    },
    {
        "name": "ImageManipulator-9.0.0-windows-setup.exe",
        "browser_download_url": "https://example.com/windows-setup.exe",
    },
    {
        "name": "ImageManipulator-9.0.0-macos.dmg",
        "browser_download_url": "https://example.com/macos.dmg",
    },
]


def _payload(tag="v9.0.0", html_url="https://github.com/release", assets=ASSETS):
    return {"tag_name": tag, "html_url": html_url, "assets": assets}


class TestVersionComparison:
    """Numeric versions beat string comparison."""

    def test_parses_prefixed_versions(self):
        assert update_checker.parse_version("v1.4.0") == (1, 4, 0)
        assert update_checker.parse_version("release-2.0") == (2, 0)

    def test_unparsable_versions(self):
        assert update_checker.parse_version("") is None
        assert update_checker.parse_version("latest") is None

    def test_detects_newer_versions(self):
        assert update_checker.is_newer("1.4.0", "1.3.0")
        assert update_checker.is_newer("v1.10.0", "1.9.9")

    def test_equal_and_older_are_not_newer(self):
        assert not update_checker.is_newer("1.3.0", "1.3.0")
        assert not update_checker.is_newer("1.2.9", "1.3.0")
        assert not update_checker.is_newer("latest", "1.3.0")


class TestDownloadSelection:
    """The direct link points at the asset for the running OS."""

    def test_platform_keys(self):
        assert update_checker.platform_asset_key("win32") == "windows"
        assert update_checker.platform_asset_key("darwin") == "macos"
        assert update_checker.platform_asset_key("linux") == "linux"

    def test_picks_each_platform_installer(self):
        assert (
            update_checker.pick_download_url(ASSETS, "win32")
            == "https://example.com/windows-setup.exe"
        )
        assert (
            update_checker.pick_download_url(ASSETS, "darwin")
            == "https://example.com/macos.dmg"
        )
        assert (
            update_checker.pick_download_url(
                ASSETS, "linux", package_kind="deb"
            )
            == "https://example.com/linux.deb"
        )
        assert (
            update_checker.pick_download_url(
                ASSETS, "linux", package_kind="rpm"
            )
            == "https://example.com/linux.rpm"
        )

    def test_falls_back_to_the_other_linux_package_type(self):
        only_rpm = [ASSETS[1]]

        assert (
            update_checker.pick_download_url(
                only_rpm, "linux", package_kind="deb"
            )
            == "https://example.com/linux.rpm"
        )

    def test_falls_back_to_the_release_page(self):
        assert (
            update_checker.pick_download_url(
                [], "linux", package_kind="deb"
            )
            == update_checker.RELEASES_PAGE
        )
        insecure = [
            {
                "name": "ImageManipulator-linux.deb",
                "browser_download_url": "http://insecure/linux.deb",
            }
        ]
        assert (
            update_checker.pick_download_url(
                insecure, "linux", package_kind="deb"
            )
            == update_checker.RELEASES_PAGE
        )


class TestLinuxPackageKind:
    """Linux installers are chosen for the running distribution family."""

    @staticmethod
    def _os_release(tmp_path, content):
        path = tmp_path / "os-release"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_debian_family(self, tmp_path):
        path = self._os_release(tmp_path, "ID=ubuntu\nID_LIKE=debian\n")

        assert (
            update_checker.linux_package_kind(
                os_release=path, which=lambda _: None
            )
            == "deb"
        )

    def test_rpm_family(self, tmp_path):
        path = self._os_release(tmp_path, "ID=fedora\n")

        assert (
            update_checker.linux_package_kind(
                os_release=path, which=lambda _: None
            )
            == "rpm"
        )

    def test_id_like_is_honoured(self, tmp_path):
        path = self._os_release(tmp_path, 'ID=custom\nID_LIKE="rhel centos"\n')

        assert (
            update_checker.linux_package_kind(
                os_release=path, which=lambda _: None
            )
            == "rpm"
        )

    def test_falls_back_to_available_tools(self, tmp_path):
        path = self._os_release(tmp_path, "")

        assert (
            update_checker.linux_package_kind(
                os_release=path,
                which=lambda name: "/usr/bin/rpm" if name == "rpm" else None,
            )
            == "rpm"
        )
        assert (
            update_checker.linux_package_kind(
                os_release=path,
                which=lambda name: "/usr/bin/dpkg" if name == "dpkg" else None,
            )
            == "deb"
        )

    def test_defaults_to_deb(self, tmp_path):
        path = self._os_release(tmp_path, "")

        assert (
            update_checker.linux_package_kind(
                os_release=path, which=lambda _: None
            )
            == "deb"
        )


class TestReleaseParsing:
    """Only a newer, well-formed release is offered."""

    def test_newer_release_returns_download_info(self):
        info = update_checker.parse_latest_release(
            _payload(),
            platform="linux",
            current_version="1.4.0",
            package_kind="deb",
        )

        assert info is not None
        assert info.version == "9.0.0"
        assert info.download_url == "https://example.com/linux.deb"
        assert info.release_url == "https://github.com/release"

    def test_same_or_older_release_is_ignored(self):
        assert (
            update_checker.parse_latest_release(
                _payload(tag="v1.4.0"), platform="linux", current_version="1.4.0"
            )
            is None
        )
        assert (
            update_checker.parse_latest_release(
                _payload(tag="v1.3.0"), platform="linux", current_version="1.4.0"
            )
            is None
        )

    def test_malformed_payload_is_ignored(self):
        assert update_checker.parse_latest_release(None) is None
        assert update_checker.parse_latest_release({"tag_name": 5}) is None
        assert update_checker.parse_latest_release({"tag_name": "latest"}) is None

    def test_missing_assets_fall_back_to_the_release_page(self):
        info = update_checker.parse_latest_release(
            _payload(assets=[]), platform="macos", current_version="1.4.0"
        )

        assert info is not None
        assert info.download_url == "https://github.com/release"

    def test_non_https_release_url_falls_back(self):
        info = update_checker.parse_latest_release(
            _payload(html_url="http://insecure"),
            platform="linux",
            current_version="1.4.0",
        )

        assert info is not None
        assert info.release_url == update_checker.RELEASES_PAGE


class TestDailyGate:
    """The automatic check runs at most once per day."""

    def test_missing_state_is_due(self):
        assert update_checker.is_check_due(None)

    def test_recent_check_is_not_due(self):
        now = 1_000_000.0

        assert not update_checker.is_check_due(now - 60, now=now)

    def test_elapsed_interval_is_due(self):
        now = 1_000_000.0

        assert update_checker.is_check_due(
            now - update_checker.CHECK_INTERVAL_SECONDS, now=now
        )

    def test_invalid_state_is_due(self):
        assert update_checker.is_check_due("yesterday")
        assert update_checker.is_check_due(True)


class TestStateFile:
    """The last successful check survives restarts."""

    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "update_check.json")

        assert update_checker.save_last_check(123.5, path=path)
        assert update_checker.load_last_check(path=path) == 123.5

    def test_missing_or_corrupt_state(self, tmp_path):
        assert update_checker.load_last_check(path=str(tmp_path / "nope.json")) is None

        corrupt = tmp_path / "update_check.json"
        corrupt.write_text("{not json", encoding="utf-8")
        assert update_checker.load_last_check(path=str(corrupt)) is None

    def test_non_numeric_state_is_ignored(self, tmp_path):
        path = tmp_path / "update_check.json"
        path.write_text('{"last_check": "yesterday"}', encoding="utf-8")

        assert update_checker.load_last_check(path=str(path)) is None


class TestNetworkBoundary:
    """The network call is the only side effect and can be mocked."""

    def test_check_for_update_uses_the_fetched_payload(self, monkeypatch):
        monkeypatch.setattr(
            update_checker,
            "fetch_latest_release",
            lambda timeout=None: _payload(),
        )

        info = update_checker.check_for_update(platform="linux")

        assert info is not None
        assert info.version == "9.0.0"

    def test_network_errors_propagate(self, monkeypatch):
        def offline(timeout=None):
            raise OSError("offline")

        monkeypatch.setattr(update_checker, "fetch_latest_release", offline)

        with pytest.raises(OSError):
            update_checker.check_for_update()
