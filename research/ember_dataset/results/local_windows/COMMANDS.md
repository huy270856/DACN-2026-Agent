# Commands executed on Windows

Run date: 2026-10-29/30, Asia/Saigon. Worktree: `work/ember-dataset-validation` on branch `feat/ember-dataset-local-validation`, based on `5e192ff14514dc261e1c43f8891caefd766eda81`. This is a run record; extraction and matrix commands refuse overwrites, so do not blindly rerun over completed outputs.

```powershell
git fetch origin feat/ember-dataset-preparation
git worktree add -b feat/ember-dataset-local-validation 'C:\Users\Admin\Documents\Codex\2026-10-23\h-y-ki-m-th-context\work\ember-dataset-validation' origin/feat/ember-dataset-preparation
curl.exe -I --max-time 45 https://ember.elastic.co/ember_dataset_2018_2.tar.bz2
$prep = 'C:\Users\Admin\Đồ án chuyên ngành\Bản trên git\.venv\Scripts\python.exe'
& $prep -m unittest discover -s research/ember_dataset -p 'test_*.py' -v
& $prep research/ember_dataset/prepare.py download --data D:\datasets\ember2018-v2
# The interrupted download was resumed using the reviewed Range implementation.
& $prep research/ember_dataset/prepare.py verify --data D:\datasets\ember2018-v2
Get-FileHash D:\datasets\ember2018-v2\ember_dataset_2018_2.tar.bz2 -Algorithm SHA256
& $prep research/ember_dataset/prepare.py audit --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-audit.json
git clone --no-checkout https://github.com/elastic/ember.git D:\datasets\ember-source
git -C D:\datasets\ember-source checkout --detach d97a0b523de02f3fe5ea6089d080abacab6ee931
curl.exe --fail --location --output D:\datasets\installers\python-3.7.9-amd64.exe https://www.python.org/ftp/python/3.7.9/python-3.7.9-amd64.exe
Get-AuthenticodeSignature D:\datasets\installers\python-3.7.9-amd64.exe
```

The signed installer ran hidden under the current user, without Administrator elevation. Arguments: `/quiet InstallAllUsers=0 TargetDir=D:\datasets\runtimes\python37 Include_launcher=0 InstallLauncherAllUsers=0 AssociateFiles=0 Shortcuts=0 PrependPath=0 AppendPath=0 Include_test=0 Include_doc=0 Include_tcltk=0 /log D:\datasets\installers\python37-install.log`. Exit code: 0.

```powershell
& D:\datasets\runtimes\python37\python.exe -m venv D:\datasets\envs\ember-v2
$research = 'D:\datasets\envs\ember-v2\Scripts\python.exe'
& $research -m pip install --upgrade pip==24.0 setuptools==68.0.0 wheel==0.42.0
& $research -m pip install --only-binary=:all: -r research/ember_dataset/requirements-research.txt
& $research -m pip install --no-deps --no-build-isolation D:\datasets\ember-source
& $research -m pip check
& $research -m pip freeze
& $research -m unittest discover -s research/ember_dataset -p 'test_*.py' -v
& $research research/ember_dataset/preflight.py --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-preflight.json
& $research research/ember_dataset/prepare.py matrix --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-matrix
& $research research/ember_dataset/check_matrix.py --data D:\datasets\ember2018-v2 --matrix D:\datasets\ember2018-matrix --output D:\datasets\ember2018-matrix-check.json --check-vectors
& $research research/ember_dataset/load_dataset.py --matrix D:\datasets\ember2018-matrix
```

No model training, raw PE download/execution, push or merge command was run. Logs and STATUS.md record actual results separately from commands.
