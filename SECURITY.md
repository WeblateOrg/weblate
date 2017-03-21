## Weblate Security

We take security very seriously at Weblate. We welcome any peer review of our
100% open source code to ensure nobody's Weblate is ever compromised or hacked.

### Where should I report security issues?

In order to give the community time to respond and upgrade we strongly urge you
report all security issues privately. Please report them by email to
michal@cihar.com. You can choose to encrypt it using his PGP key
`9C27B31342B7511D`.

### Django

We're heavily depending on Django for many things (escaping in templates,
CSRF protection and so on). In case you find vulnerability which is affecting
Django in general, please report it directly to Django:

https://docs.djangoproject.com/en/dev/internals/security/
