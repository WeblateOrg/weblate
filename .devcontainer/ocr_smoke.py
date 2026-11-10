# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify prepared OCR assets in a container with networking disabled."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from environment import Environment


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    env = Environment(root, "tests", "compose")
    container = env.output("ps", "--quiet", "developer")
    image = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Image}}", container], text=True
    ).strip()
    code = """
from pathlib import Path
from tesserocr import PyTessBaseAPI
models = Path('/app/data/tests/data-test/cache/tesseract')
for language in ('eng', 'osd'):
    if not (models / f'{language}.traineddata').is_file():
        raise RuntimeError(f'Missing prepared OCR model: {language}')
with PyTessBaseAPI(path=str(models), lang='eng') as api:
    api.SetImageFile('weblate/trans/tests/data/screenshot.png')
    if 'Hello, world!' not in api.GetUTF8Text():
        raise RuntimeError('Prepared OCR models failed recognition')
print('OCR recognition passed without network access')
"""
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--volumes-from",
            container,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            str(root),
            "--entrypoint",
            "/app/venv/bin/python",
            image,
            "-c",
            code,
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
