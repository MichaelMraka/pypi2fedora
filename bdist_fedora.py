"""
Modify the Distutils 'bdist_rpm' command (create RPM source and binary
distributions) to be able of automatic rebuild in Fedora's COPR and
fit better to Fedora packaging Guidlines.
"""

import distutils.command
import distutils.command.bdist_rpm
import re
import time

DEFAULT_PYTHON_VERSION = '2'

bdist_rpm_orig = distutils.command.bdist_rpm.bdist_rpm
class bdist_fedora (bdist_rpm_orig):
    def finalize_package_data (self):
        bdist_rpm_orig.finalize_package_data(self)

        # shorten description on first newline after approx 10 lines
        cut = self.distribution.metadata.long_description.find('\n', 80*8)
        if cut > -1:
            self.distribution.metadata.long_description = \
                self.distribution.metadata.long_description[:cut] + '\n...'

        # requires
        self.requires = self.requires or self._install_requires()
        
        # buildrequires
        self.build_requires = self.build_requires or self._build_requires()

    def _make_spec_file(self):
        import pdb; pdb.set_trace()
        spec_file = [
            '%define upstream_name ' + self.distribution.get_name(),
            '%define version ' + self.distribution.get_version().replace('-','_'),
            '%define unmangled_version ' + self.distribution.get_version(),
            ]

        py_versions = self._python_versions()
        spec_file.extend(['%bcond_' + ('without' if v in py_versions else 'with')
                          + ' python' + v for v in ['2', '3']])
        spec_file.append('%define sphinx_build %{?with_python2:sphinx-build}'
                         '%{!?with_python2:sphinx-build-3}')

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

        for field in ('Vendor',
                      'Packager',
                      'Requires',
                      'Provides',
                      'Conflicts',
                      'Obsoletes',
                      ):
            val = getattr(self, field.lower())
            if isinstance(val, list):
                spec_file.extend(['%s: %s' % (field, v) for v in val])
            elif val is not None:
                spec_file.append('%s: %s' % (field, val))

        if self.build_requires:
            spec_file.extend(['BuildRequires: %s' % br
                              for br in self.build_requires])

        spec_file.extend([
            '',
            '%description',
            self.distribution.get_long_description()
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
                              '%endif',
                             ])

        build_cmd = ['%if %{with python2}',
                     '  %{py2_build}',
                     '%endif',
                     '%if %{with python3}',
                     '  %{py3_build}',
                     '%endif',
                     'for i in doc docs ; do',
                     '  [ -d "$i" ] && %{sphinx_build} "$i" html',
                     'done',
                    ]
        install_cmd = ['%if %{with python2}',
                       '  %{py2_install}',
                       '%endif',
                       '%if %{with python3}',
                       '  %{py3_install}',
                       '%endif',
                     ]


        script_options = [
            ('prep', 'prep_script', "%autosetup -n %{upstream_name}-%{unmangled_version}"),
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

        for ver in ['2','3']:
            ver_name = self._rpm_name(self.distribution.get_name(), ver)
            sitearch = '%{python' + ver + '_sitearch}/%{upstream_name}'
            spec_file.extend(['',
                              '%if %{with python' + ver + '}',
                              '%files -n ' + ver_name,
                              '%defattr(-,root,root)',
                              sitearch,
                              sitearch + '-%{version}-py?.?.egg-info',
                              '%endif',
                             ])
            if self.doc_files:
                spec.append('%doc ' + ' '.join(self.doc_files))

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

    def _get_license(self):
        return self.distribution.get_license()

    def _python_versions(self):
        """ Find python version from classifiers."""
        versions = set()
        for classifier in self.distribution.metadata.classifiers:
            if classifier.startswith('Programming Language :: Python ::'):
                ver = classifier.split('::')[-1]
                major = ver.split('.')[0].strip()
                if major:
                    versions.add(major)
        if not versions:
            versions = set(DEFAULT_PYTHON_VERSION)
        return sorted(versions)

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

