; Inno Setup script for the Image Manipulator Windows installer.
; Build with:
;   ISCC.exe /DMyAppVersion=1.6.0 /DRepoRoot=<repo> \
;       /DSourceExe=<repo>\dist\ImageManipulator-windows.exe \
;       /DOutputDir=<repo>\dist\installers packaging\windows\image-manipulator.iss

#define MyAppName "Image Manipulator"
#define MyAppPublisher "Pavlenko Evgeniy"
#define MyAppURL "https://github.com/PavlenkoEvgeniy/python-image-manipulator"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef RepoRoot
  #define RepoRoot "."
#endif
#ifndef SourceExe
  #define SourceExe "dist\ImageManipulator-windows.exe"
#endif
#ifndef OutputDir
  #define OutputDir "dist\installers"
#endif

[Setup]
AppId={{B7A2C0E4-5D3F-4E86-9C1A-2F7D8B4E6A31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\Image Manipulator
DefaultGroupName=Image Manipulator
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir={#OutputDir}
OutputBaseFilename=ImageManipulator-{#MyAppVersion}-windows-setup
SetupIconFile={#RepoRoot}\assets\icon.ico
UninstallDisplayIcon={app}\ImageManipulator.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
VersionInfoVersion={#MyAppVersion}.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "ImageManipulator.exe"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Image Manipulator"; Filename: "{app}\ImageManipulator.exe"
Name: "{autodesktop}\Image Manipulator"; Filename: "{app}\ImageManipulator.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ImageManipulator.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
