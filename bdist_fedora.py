"""
Modify the Distutils 'bdist_rpm' command (create RPM source and binary
distributions) to be able of automatic rebuild in Fedora's COPR and
fit better to Fedora packaging Guidlines.
"""

import distutils.command
import distutils.command.bdist_rpm
import re

bdist_rpm_orig = distutils.command.bdist_rpm.bdist_rpm
class bdist_fedora (bdist_rpm_orig):
    def finalize_package_data (self):
        bdist_rpm_orig.finalize_package_data(self)
        import pdb; pdb.set_trace()
        
        py_ver = '3'
        # rpm name 
        self.distribution.metadata.name = self._rpm_name(
                self.distribution.get_name(), py_ver)
        
        # requires
        requires = (self.requires or []) + self._install_requires()
        if requires:
            self.requires = [self._rpm_name(name, py_ver) for name in requires]
        
        # buildrequires
        build_requires = (self.build_requires or []) + self._build_requires()
        if build_requires:
            self.build_requires = [self._rpm_name(name, py_ver)
                               for name in build_requires]

    @staticmethod
    def _rpm_name(name, pyversion, default=None):
        """
        Return versioned name of a package.
        E.g. python-foo, 26  -> python26-foo
             foo 3           -> python3-foo
             python2-foo, 3  -> python3-foo
             foo-python2, 26 -> python26-foo
        If version is equal to default then no version number is added.
        """
        if name == 'python2-devel':
            # an exception; don't rename python2-devel
            return name

        for regexp in [r'^python(?P<ver>\d*)-(?P<name>.*)$',
                       r'^(?P<name>.*)-python(?P<ver>\d*)$']:
            match = re.match(regexp, name) 
            if match:
                name = match.group('name')

        name = name.replace('.', "-")

        if not pyversion or pyversion == default:
            pyversion = ''
        return 'python%s-%s' % (pyversion, name)

    def _install_requires(self):
        install_requires = self.distribution.install_requires or []
        if (self.distribution.entry_points
            and 'setuptools' not in install_requires):
            install_requires.append('setuptools')
        return install_requires

    def _build_requires(self):
        build = self.distribution.setup_requires or []
        if 'setuptools' in build:
            build.remove('setuptools')
        test = self.distribution.tests_require or []
        return build + test

distutils.command.bdist_rpm.bdist_rpm = bdist_fedora

if __name__ == '__main__':
    import sys
    import os.path

    # run script given as a first argument
    del sys.argv[0]     # remove ourselves from argument list

    setup = sys.argv[0]
    if setup.endswith('.py'):
        setup = setup[:-3]
    sys.path.insert(0, os.path.dirname(setup))
    __import__(os.path.basename(setup))


