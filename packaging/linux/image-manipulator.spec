Name:           image-manipulator
Version:        @VERSION@
Release:        1
Summary:        Resize images and overlay text in a single pass
License:        MIT
URL:            https://github.com/PavlenkoEvgeniy/python-image-manipulator
BuildArch:      %{_arch}

# The PyInstaller one-file payload follows the ELF image; stripping it could
# damage the archive, so skip the post-install strip and byte-compile steps.
%global __os_install_post %{nil}

%description
Image Manipulator resizes images and overlays text in a single pass.
The application is a self-contained PyInstaller build.

%install
install -Dm755 %{_sourcedir}/ImageManipulator %{buildroot}%{_bindir}/image-manipulator
install -Dm644 %{_sourcedir}/image-manipulator.desktop %{buildroot}%{_datadir}/applications/image-manipulator.desktop
install -Dm644 %{_sourcedir}/image-manipulator.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/image-manipulator.png

%files
%{_bindir}/image-manipulator
%{_datadir}/applications/image-manipulator.desktop
%{_datadir}/icons/hicolor/256x256/apps/image-manipulator.png
