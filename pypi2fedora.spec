Name:		pypi2fedora
Version:	0.9.1
Release:	1%{?dist}
Summary:	Convert PyPI packages to srpm suitable for Fedora COPR

Group:		Development/Tools
License:	Python or LGPLv2+
URL:		https://github.com/MichaelMraka/pypi2fedora
Source0:	https://github.com/MichaelMraka/pypi2fedora/archive/%{name}-%{version}.tar.gz

BuildArch:	noarch
BuildRequires:	python3-devel
Requires:	python3-libs
Requires:	python3-pip
Requires:	python3-setuptools

%description
Convert PyPI packages to srpm suitable for Fedora COPR.

%prep
%setup -q


%build

%install
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{python3_sitelib}
install -m 755 pypi2fedora %{buildroot}%{_bindir}/
cp -a modules/pypi2fedora %{buildroot}%{python3_sitelib}


%files
%{_bindir}/*
%{python3_sitelib}/*


%changelog
* Fri Feb 26 2016 Michael Mraka <michael.mraka@redhat.com> 0.9.1-1
- initial rpm build


