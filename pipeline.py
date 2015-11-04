from setuptools import archive_util

import glob
import os
import pip
import shutil
import sys
import tempfile
import bdist_fedora

if __name__ == '__main__':
    package_name = sys.argv[1]

    curdir = os.getcwd()
    temp = tempfile.mkdtemp(prefix='pipeline.')
    tempdir = {}

    try:
        for d in ['source', 'target']:
            tempdir[d] = os.path.join(temp, d)
            os.mkdir(tempdir[d])
        pip.main(['install', '--disable-pip-version-check', '--no-deps', '--download',
                  tempdir['source'], package_name])

        try:
            package_sources = glob.glob(os.path.join(tempdir['source'], '*'))[0]
        except IndexError:
            print("Package source not found.")
            raise SystemExit(2)

        archive_util.unpack_archive(package_sources, tempdir['target'])

        try:
            setup_py = glob.glob(os.path.join(tempdir['target'], '*', 'setup.py'))[0]
        except IndexError:
            print("setup.py not found; maybe this is not a source archive.")
            raise SystemExit(3)

        os.chdir(os.path.dirname(setup_py))
        bdist_fedora.run_setup(setup_py, 'bdist_rpm', '--source', '--quiet',
                               '--dist-dir', curdir)

    finally:
        shutil.rmtree(temp)
