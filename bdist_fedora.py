"""
Modify the Distutils 'bdist_rpm' command (create RPM source and binary
distributions) to be able of automatic rebuild in Fedora's COPR and
fit better to Fedora packaging Guidlines.
"""

import distutils.command
import distutils.command.bdist_rpm
import glob
import re
import time

DEFAULT_PYTHON_VERSION = '2'
DOC_PATTERNS = ['AUTHOR*', 'COPYING*', 'LICENS*', 'README*']
SPHINX_PATTERNS = ['doc', 'docs']

bdist_rpm_orig = distutils.command.bdist_rpm.bdist_rpm
class bdist_fedora (bdist_rpm_orig):
    def finalize_package_data (self):
        bdist_rpm_orig.finalize_package_data(self)

        # shorten description on first newline after approx 10 lines
        if self.distribution.metadata.long_description:
            cut = self.distribution.metadata.long_description.find('\n', 80*8)
            if cut > -1:
                self.distribution.metadata.long_description = \
                    self.distribution.metadata.long_description[:cut] + '\n...'

        # build reqs
        self._build_requires = self.build_requires or (
                               self._list(getattr(self.distribution, 'setup_requires', []))
                               + self._list(getattr(self.distribution, 'tests_require', [])))
        
        # requires, conflicts
        self._requires = self.requires or \
                         self._list(getattr(self.distribution, 'install_requires', []))
        self._conflicts = [dep.replace('!=', '=')
                           for dep in self._requires if '!=' in dep]
        self._requires = [dep.replace('==', '=')
                          for dep in self._requires if '!=' not in dep]
        if (getattr(self.distribution, 'entry_points', None)
            and 'setuptools' not in self._requires):
            self._requires.append('setuptools')

    def _make_spec_file(self):
        spec_file = [
            '%define upstream_name ' + self.distribution.get_name(),
            '%define version ' + self.distribution.get_version().replace('-','_'),
            '%define unmangled_version ' + self.distribution.get_version(),
            ]

        py_versions = self._python_versions()
        for ver in ['2', '3']:
            enabled = 'enabled' if ver in py_versions else 'disabled'
            opt = 'without' if ver in py_versions else 'with'
            comment = ('# python{v} support {en} by default; rebuild with '
                       + '"rpmbuild --{opt} python{v} ..." to change it').format(
                        v=ver, en=enabled, opt=opt)
            spec_file.extend([comment,
                              '%bcond_' + opt + ' python' + ver])

        spec_file.extend(['',
            'Name:      python-%{upstream_name}',
            'Version:   %{version}',
            'Release:   ' + self.release.replace('-','_') + '%{dist}',
            'Source0:   %{upstream_name}-%{unmangled_version}.tar.'
                + ('bz2' if self.use_bzip2 else 'gz'),
            'Group:     ' + self.group,
            'License:   ' + self._get_license(),
            'Summary:   ' + self.distribution.get_description(),
        ])

        if not self.force_arch:
            # noarch if no extension modules
            if not self.distribution.has_ext_modules():
                spec_file.append('BuildArch: noarch')
        else:
            spec_file.append('BuildArch: %s' % self.force_arch)

        if self.distribution.get_url() != 'UNKNOWN':
            spec_file.append('Url: ' + self.distribution.get_url())

        if self.distribution_name:
            spec_file.append('Distribution: ' + self.distribution_name)

        if self.icon:
            spec_file.append('Icon: ' + os.path.basename(self.icon))

        if self.no_autoreq:
            spec_file.append('AutoReq: 0')

        if self.vendor:
            spec_file.append('Vendor: ' + self.vendor)

        if self.packager:
            spec_file.append('Packager: ' + self.packager)

        spec_file.extend([
            '',
            '%description',
            self.distribution.get_long_description()
            ])

        sphinx_dirs = [f for pat in SPHINX_PATTERNS for f in glob.glob(pat)]
        if sphinx_dirs:
            doc_name = 'python-%s-doc' % self.distribution.get_name()
            descr = 'Documentation for ' + self.distribution.get_name()
            spec_file.extend(['',
                              '%package -n ' + doc_name,
                              'Summary: ' + descr,
                              '%description -n ' + doc_name,
                              descr,
                              '',
                              '%define sphinx_build %{?with_python2:sphinx-build}'
                                  '%{!?with_python2:sphinx-build-3}'
                             ])

        for ver in ['2', '3']:
            ver_name = self._rpm_name(self.distribution.get_name(), ver)
            spec_file.extend(['',
                              '%if %{with python' + ver + '}',
                              '%package -n ' + ver_name,
                              'Summary: ' + self.distribution.get_description(),
                              '%{?python_provide:%python_provide ' + ver_name + '}',
                              '',
                              '%description -n ' + ver_name,
                              self.distribution.get_long_description(),
                              '',
                              'BuildRequires: ' + self._rpm_name('python-devel', ver),
                             ])
            for dep in self._build_requires:
                spec_file.append('BuildRequires: ' + self._rpm_dep(dep, ver,
                                                                   DEFAULT_PYTHON_VERSION))
            if sphinx_dirs:
                spec_file.append('BuildRequires: ' + self._rpm_name('python-sphinx', ver,
                                                                    DEFAULT_PYTHON_VERSION))
            for dep in self._requires:
                spec_file.append('Requires: ' + self._rpm_dep(dep, ver,
                                                              DEFAULT_PYTHON_VERSION))
            for dep in self._conflicts:
                spec_file.append('Conflicts: ' + self._rpm_dep(dep, ver,
                                                               DEFAULT_PYTHON_VERSION))
            if self.provides:
                for dep in self.provides:
                    spec_file.append('Provides: ' + self._rpm_dep(dep, ver,
                                                                  DEFAULT_PYTHON_VERSION))
            if self.obsoletes:
                for dep in self.obsoletes:
                    spec_file.append('Obsoletes: ' + self._rpm_dep(dep, ver,
                                                                   DEFAULT_PYTHON_VERSION))
            spec_file.append('%endif')


        prep_cmd =  ['%autosetup -n %{upstream_name}-%{unmangled_version}',
                     '# Remove bundled egg-info',
                     'rm -rf %{upstream_name}.egg-info',
                    ]
        build_cmd = ['%if %{with python2}',
                     '  %{py2_build}',
                     '%endif',
                     '%if %{with python3}',
                     '  %{py3_build}',
                     '%endif',
                    ]
        if sphinx_dirs:
            build_cmd.extend(['%{sphinx_build} ' + dir + ' html' for dir in sphinx_dirs])
            build_cmd.append('rm -rf html/.{doctrees,buildinfo}')

        install_cmd = ['%if %{with python3}',
                       '  %{py3_install \--record=.python3-installfiles.txt}',
                       '%endif',
                       '%if %{with python2}',
                       '  %{py2_install \--record=.python2-installfiles.txt}',
                       '%endif',
                     ]


        script_options = [
            ('prep', 'prep_script', prep_cmd),
            ('build', 'build_script', build_cmd),
            ('install', 'install_script', install_cmd),
            ('clean', 'clean_script', "rm -rf $RPM_BUILD_ROOT"),
            ('verifyscript', 'verify_script', None),
            ('pre', 'pre_install', None),
            ('post', 'post_install', None),
            ('preun', 'pre_uninstall', None),
            ('postun', 'post_uninstall', None),
        ]

        for (rpm_opt, attr, default) in script_options:
            # Insert contents of file referred to, if no file is referred to
            # use 'default' as contents of script
            val = getattr(self, attr)
            if val or default:
                spec_file.extend([
                    '',
                    '%' + rpm_opt,])
                if val:
                    spec_file.extend(open(val, 'r').read().split('\n'))
                elif isinstance(default, list):
                    spec_file.extend(default)
                else:
                    spec_file.append(default)

        if sphinx_dirs:
            spec_file.extend(['',
                              '%files -n ' + doc_name,
                              '%defattr(-,root,root)',
                              '%doc html',
                             ])

        doc_files = [f for pat in DOC_PATTERNS for f in glob.glob(pat)]
        for ver in ['2','3']:
            ver_name = self._rpm_name(self.distribution.get_name(), ver)
            spec_file.extend(['',
                              '%if %{with python' + ver + '}',
                              '%files -n ' + ver_name + ' -f .python' + ver + '-installfiles.txt',
                              '%defattr(-,root,root)',
                              '%doc ' + ' '.join(doc_files),
                             ])
            spec_file.append('%endif')

        # changelog
        spec_file.extend(['', '%changelog'])
        if self.changelog:
            spec_file.extend(self.changelog)
        else:
            # automatic changelog
            spec_file.extend([time.strftime("* %a %b %d %Y ", time.localtime())
                              + (self.packager or '') + ' - %{version}-%{release}',
                              '- Automatic rebuild from upstream'])

        return spec_file

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

    def _rpm_dep(self, dep, pyversion, default=None):
        m = re.match(r'([^<=>]*)(.*)', dep)
        return self._rpm_name(m.group(1), pyversion, default) + m.group(2)

    def _get_license(self):
        return self.distribution.get_license()

    def _python_versions(self):
        """ Find python version from classifiers."""
        versions = set()
        for classifier in self._list(self.distribution.metadata.classifiers):
            if classifier.startswith('Programming Language :: Python ::'):
                ver = classifier.split('::')[-1]
                major = ver.split('.')[0].strip()
                if major:
                    versions.add(major)
        if not versions:
            versions = set(DEFAULT_PYTHON_VERSION)
        return sorted(versions)

    @staticmethod
    def _list(var):
        if var is None:
            return []
        elif not isinstance(var, list):
            raise DistutilsOptionError, "%s is not a list" % var
        return var


distutils.command.bdist_rpm.bdist_rpm = bdist_fedora

if __name__ == '__main__':
    import os.path
    import runpy
    import sys

    # run script given as a first argument
    del sys.argv[0]     # remove ourselves from argument list

    setup = sys.argv[0]
    if setup.endswith('.py'):
        setup = setup[:-3]
    sys.path.insert(0, os.path.dirname(setup))
    runpy.run_module(setup, run_name='__main__', alter_sys=True)

