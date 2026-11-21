# Third-party notices

Prism Monitor is GPL-3.0-only software (see LICENSE). Releases before 1.1.0 of this repository were published under the MIT licence; that earlier code remains available under MIT in the git history.

## Qt for Python / PySide6 / Shiboken6 / Qt

Version pinned: 6.10.1. Copyright The Qt Company Ltd. and contributors. PySide6 is available under `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; this GPLv3 application uses the GPLv3 terms. Unmodified Qt licence texts are in `licenses/Qt-license-texts/`. Source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.1-src/

## Python

Python Software Foundation and contributors. PSF licence: `licenses/Python-PSF-2.0.txt`.

## PyInstaller (build tool and bootloader)

Version pinned: 6.17.0. GPL-2.0-or-later with the bootloader exception: `licenses/PyInstaller-COPYING.txt`. https://github.com/pyinstaller/pyinstaller/tree/v6.17.0

## Intel PresentMon 2.6.0 (Windows game FPS)

`vendor/presentmon/PresentMon.exe`, the unmodified console release from https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0 (SHA-256 b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af), fetched by `tools/fetch_sensors.py`. MIT licence: `licenses/PresentMon-MIT.txt`.

## LibreHardwareMonitorLib 0.9.6 (Windows sensor helper)

https://github.com/LibreHardwareMonitor/LibreHardwareMonitor, release v0.9.6, fetched and checksum-verified by `tools/fetch_monitor_deps.py`. Mozilla Public License 2.0, copied to `licenses/LibreHardwareMonitor-MPL-2.0.txt` in the Windows package. The unmodified library and its bundled .NET dependency assemblies run in a separate helper process, `PrismSensorHost.exe`, built from `monitor/sensorhost/PrismSensorHost.cs`. The helper reads ring-0 sensors through the PawnIO driver, which Prism Monitor does not install.

## Barlow font (Poster look)

`prism_monitor/fonts/Barlow-{Regular,SemiBold,Bold}.ttf`, unmodified, from https://github.com/jpt/barlow. Copyright 2017 The Barlow Project Authors. SIL Open Font License 1.1: `prism_monitor/fonts/OFL-barlow.txt` (also `licenses/Barlow-OFL.txt`).

## Vulkan-Headers 1.4.309 (Linux game FPS layer, build time only)

`tools/build_fps_layer.py` downloads the official Khronos release, checks its SHA-256, and uses only its headers to compile `monitor/vklayer/prism_fps_layer.c`. Apache-2.0. The headers are not redistributed.
