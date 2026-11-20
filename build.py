"""Build a portable folder + ZIP for the OS this runs on (Windows or Linux)."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
windows = sys.platform == 'win32'
if windows:
    subprocess.run([sys.executable, str(root / 'tools' / 'fetch_presentmon.py')], cwd=root, check=True)
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
                '--name', 'PrismMonitor', str(root / 'main.py')], cwd=root, check=True)
bundle = root / 'dist' / 'PrismMonitor'
for name in ('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md'):
    shutil.copy2(root / name, bundle / name)
shutil.copytree(root / 'licenses', bundle / 'licenses', dirs_exist_ok=True)
if windows:
    shutil.copytree(root / 'vendor' / 'presentmon', bundle / 'tools' / 'presentmon', dirs_exist_ok=True)
else:
    for name in ('prism-monitor-run', 'install-linux.sh'):
        shutil.copy2(root / 'scripts' / name, bundle / name)
notices = bundle / 'licenses' / 'installed-package-notices'
for distribution in distributions():
    package = distribution.metadata['Name']
    for f in distribution.files or []:
        if 'dist-info' in str(f) and (f.name in ('METADATA', 'COPYING', 'LICENSE', 'LICENSE.txt', 'LICENSE.md')
                                      or 'licenses' in f.parts):
            source = Path(distribution.locate_file(f))
            if source.is_file():
                target = notices / package / str(f)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
name = 'PrismMonitor-windows' if windows else 'PrismMonitor-linux'
archive = shutil.make_archive(str(root / 'dist' / name), 'zip', root / 'dist', 'PrismMonitor')
print(f'Portable folder: {bundle}\nZIP: {archive}')
