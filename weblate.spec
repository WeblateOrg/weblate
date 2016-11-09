%{!?python_sitelib: %global python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%define WLDIR %{_datadir}/weblate
%define WLDATADIR %{_localstatedir}/lib/weblate
%define WLETCDIR %{_sysconfdir}/weblate
Name:           weblate
%define _name Weblate
Version:        2.10
Release:        0
Summary:        Web-based translation tool
License:        GPL-3.0+
Group:          Productivity/Networking/Web/Frontends
Url:            https://weblate.org/
Source0:        http://dl.cihar.com/weblate/%{_name}-%{version}.tar.xz
BuildRequires:  bitstream-vera
BuildRequires:  git
BuildRequires:  graphviz
BuildRequires:  graphviz-gd
BuildRequires:  mercurial
BuildRequires:  python-Babel
BuildRequires:  python-Django >= 1.7
BuildRequires:  python-Pillow
BuildRequires:  python-Sphinx
BuildRequires:  python-alabaster
BuildRequires:  python-dateutil
BuildRequires:  python-defusedxml
BuildRequires:  python-django-crispy-forms >= 1.4.0
BuildRequires:  python-django_compressor
BuildRequires:  python-djangorestframework >= 3.3
BuildRequires:  python-httpretty
BuildRequires:  python-python-social-auth >= 0.2
BuildRequires:  python-selenium
BuildRequires:  python-sphinxcontrib-httpdomain
BuildRequires:  python-whoosh >= 2.5.2
BuildRequires:  translate-toolkit >= 1.14.0
Requires:       apache2-mod_wsgi
Requires:       cron
Requires:       git
Requires:       python-Babel
Requires:       python-defusedxml
Requires:       python-Django >= 1.7
Requires:       python-django_compressor
Requires:       python-djangorestframework >= 3.3
Requires:       python-Pillow
Requires:       python-dateutil
Requires:       python-django-crispy-forms >= 1.4.0
Requires:       python-python-social-auth >= 0.2
Requires:       python-whoosh >= 2.5.2
Requires:       translate-toolkit >= 1.14.0
Recommends:     python-MySQL-python
Recommends:     python-psycopg2
Recommends:     python-pyuca
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
* Propagation of translations across components (for different branches)
* Tight git integration - every change is represented by Git commit
* Usage of Django's admin interface
* Upload and automatic merging of po files
* Links to source files for context
* Allows to use machine translation services
* Message quality checks
* Tunable access control
* Wide range of supported translation formats (Getext, Qt, Java, Windows, Symbian and more)

%prep
%setup -q -n %{_name}-%{version}

%build
make %{?_smp_mflags} -C docs html
# Copy example settings
cp weblate/settings_example.py weblate/settings.py
# Set correct directories in settings
sed -i 's@^BASE_DIR = .*@BASE_DIR = "%{WLDIR}/weblate"@g' weblate/settings.py
sed -i 's@^DATA_DIR = .*@DATA_DIR = "%{WLDATADIR}"@g' weblate/settings.py
sed -i "s@/usr/share/weblate/data@%{WLDATADIR}@" examples/apache.conf

%install
install -d %{buildroot}/%{WLDIR}
install -d %{buildroot}/%{WLETCDIR}

# Copy all files
cp -a . %{buildroot}/%{WLDIR}
# Remove test data
rm -rf %{buildroot}/%{WLDIR}/data-test

# We ship this separately
rm -rf %{buildroot}/%{WLDIR}/docs
rm -f %{buildroot}/%{WLDIR}/README.rst \
    %{buildroot}/%{WLDIR}/ChangeLog \
    %{buildroot}/%{WLDIR}/COPYING \
    %{buildroot}/%{WLDIR}/INSTALL

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

%post
# Static files
%{WLDIR}/manage.py collectstatic --noinput

%check
export LANG=en_US.UTF-8
# Collect static files for testsuite
./manage.py collectstatic --noinput --settings=weblate.settings_test -v 2
# Run the testsuite
./manage.py test --settings=weblate.settings_test -v 2

%files
%defattr(-,root,root)
%doc docs/_build/html
%doc README.rst
%config(noreplace) %{_sysconfdir}/weblate
%config(noreplace) %{_sysconfdir}/apache2
%{WLDIR}
%attr(0755,wwwrun,www) %{WLDATADIR}

%changelog
