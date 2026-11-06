Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!include "MUI2.nsh"

Name "NeoCatCraftLauncher"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\NeoCatCraftLauncher"
InstallDirRegKey HKCU "Software\NeoCatCraftLauncher" "InstallDir"
Icon "${ICON_FILE}"
UninstallIcon "${ICON_FILE}"

!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"
!define MUI_WELCOMEPAGE_TITLE "安装 NeoCatCraftLauncher"
!define MUI_WELCOMEPAGE_TEXT "启动器已内置 Python 与运行依赖，安装后无需单独安装 Python。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\NeoCatCraftLauncher.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 NeoCatCraftLauncher"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "NeoCatCraftLauncher"
VIAddVersionKey /LANG=2052 "CompanyName" "NeoCatCraft"
VIAddVersionKey /LANG=2052 "FileDescription" "NeoCatCraft Minecraft Launcher"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"

Section "NeoCatCraftLauncher" MainSection
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\NeoCatCraftLauncher"
  CreateShortcut "$SMPROGRAMS\NeoCatCraftLauncher\NeoCatCraftLauncher.lnk" "$INSTDIR\NeoCatCraftLauncher.exe" "" "$INSTDIR\NeoCatCraftLauncher.exe" 0
  CreateShortcut "$SMPROGRAMS\NeoCatCraftLauncher\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\NeoCatCraftLauncher.lnk" "$INSTDIR\NeoCatCraftLauncher.exe" "" "$INSTDIR\NeoCatCraftLauncher.exe" 0

  WriteRegStr HKCU "Software\NeoCatCraftLauncher" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "DisplayName" "NeoCatCraftLauncher"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "Publisher" "NeoCatCraft"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "DisplayIcon" "$INSTDIR\NeoCatCraftLauncher.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\NeoCatCraftLauncher.lnk"
  Delete "$SMPROGRAMS\NeoCatCraftLauncher\NeoCatCraftLauncher.lnk"
  Delete "$SMPROGRAMS\NeoCatCraftLauncher\Uninstall.lnk"
  RMDir "$SMPROGRAMS\NeoCatCraftLauncher"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeoCatCraftLauncher"
  DeleteRegKey HKCU "Software\NeoCatCraftLauncher"
  RMDir /r "$INSTDIR"
SectionEnd
