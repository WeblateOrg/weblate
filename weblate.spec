%{!?python_sitelib: %global python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%define WLDIR %{_datadir}/weblate
%define WLDATADIR %{_localstatedir}/lib/weblate
%define WLETCDIR /%{_sysconfdir}/weblate
Name:           weblate
Version:        2.3
Release:        0
Summary:        Web-based translation tool
License:        GPL-3.0+
Group:          Productivity/Networking/Web/Frontends
Url:            http://weblate.org/
Source:         %{name}-%{version}.tar.bz2
Source1:        test-base-repo.git.tar.bz2
BuildRequires:  bitstream-vera
BuildRequires:  git
BuildRequires:  graphviz
BuildRequires:  graphviz-gd
BuildRequires:  python-Babel
BuildRequires:  python-Django >= 1.7
BuildRequires:  python-Pillow
BuildRequires:  python-Sphinx
BuildRequires:  python-dateutil
BuildRequires:  python-django-crispy-forms >= 1.4.0
BuildRequires:  python-httpretty
BuildRequires:  python-python-social-auth >= 0.2
BuildRequires:  python-selenium
BuildRequires:  python-sphinxcontrib-httpdomain
BuildRequires:  python-whoosh >= 2.5.2
BuildRequires:  translate-toolkit >= 1.10.0
Requires:       apache2-mod_wsgi
Requires:       cron
Requires:       git
Requires:       python-Babel
Requires:       python-Django >= 1.7
Requires:       python-Pillow
Requires:       python-dateutil
Requires:       python-django-crispy-forms >= 1.4.0
Requires:       python-python-social-auth >= 0.2
Requires:       python-whoosh >= 2.5.2
Requires:       translate-toolkit >= 1.10.0
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
BuildArch:      noarch
%py_requires

%description
Weblate is a free web-based translation tool with tight version control
integration. It features simple and clean user interface, propagation of
translations across components, quality checks and automatic linking to source
files.

List of features includes:

* Easy web based translation
* Propagation of translations across sub-projects (for different branches)
* Tight git integration - every change is represented by Git commit
* Usage of Django's admin interface
* Upload and automatic merging of po files
* Links to source files for context
* Allows to use machine translation services
* Message quality checks
* Tunable access control
* Wide range of supported translation formats (Getext, Qt, Java, Windows, Symbian and more)

%prep
%setup -q
mkdir weblate/test-repos/
cd weblate/test-repos/
tar xvf %{SOURCE1}
cd ../..

%build
make -C docs html
cp weblate/settings_example.py weblate/settings.py
sed -i 's@^BASE_DIR = .*@BASE_DIR = "%{WLDIR}/weblate"@g' weblate/settings.py
sed -i 's@^DATA_DIR = .*@DATA_DIR = "%{WLDATADIR}"@g' weblate/settings.py
sed -i "s@'ENGINE': 'django.db.backends.sqlite3'@'ENGINE': 'django.db.backends.mysql'@" weblate/settings.py
sed -i "s@'NAME': 'weblate.db'@'NAME': 'weblate'@" weblate/settings.py
sed -i 's@/usr/lib/python.*/site-packages@%{python_sitelib}@g' examples/apache.conf

%install
install -d %{buildroot}/%{WLDIR}
install -d %{buildroot}/%{WLETCDIR}

# Copy all files
cp -a . %{buildroot}/%{WLDIR}

# We ship this separately
rm -rf %{buildroot}/%{WLDIR}/docs
rm -f %{buildroot}/%{WLDIR}/README.rst \
    %{buildroot}/%{WLDIR}/ChangeLog \
    %{buildroot}/%{WLDIR}/COPYING \
    %{buildroot}/%{WLDIR}/INSTALL
rm -f \
    %{buildroot}/%{WLDIR}/.coveragerc \
    %{buildroot}/%{WLDIR}/.landscape.yaml \
    %{buildroot}/%{WLDIR}/.travis.yml \
    %{buildroot}/%{WLDIR}/.pep8 \
    %{buildroot}/%{WLDIR}/.scrutinizer.yml \
    %{buildroot}/%{WLDIR}/pylint.rc


# Byte compile python files
%py_compile %{buildroot}/%{WLDIR}

# Move configuration to etc
mv %{buildroot}/%{WLDIR}/weblate/settings.py %{buildroot}/%{WLETCDIR}/
ln -s %{WLETCDIR}/settings.py %{buildroot}/%{WLDIR}/weblate/settings.py

# Apache config
install -d %{buildroot}/%{_sysconfdir}/apache2/vhosts.d/
install -m 644 examples/apache.conf %{buildroot}/%{_sysconfdir}/apache2/vhosts.d/weblate.conf

# Whoosh index dir
install -d %{buildroot}/%{WLDATADIR}
install -d %{buildroot}/%{WLDATADIR}/whoosh-index
install -d %{buildroot}/%{WLDATADIR}/repos

%check
./manage.py test --settings=weblate.settings_test -v 2

%files
%defattr(-,root,root)
%doc docs/_build/html
%doc README.rst
%config(noreplace) /%{_sysconfdir}/weblate
%config(noreplace) /%{_sysconfdir}/apache2
%{WLDIR}
%attr(0755,wwwrun,www) %{WLDATADIR}
%attr(0755,wwwrun,www) %{WLDATADIR}/whoosh-index
%attr(0755,wwwrun,www) %{WLDATADIR}/repos

%changelog
