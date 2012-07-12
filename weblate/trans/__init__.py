from south.signals import post_migrate

def create_permissions_compat(app, **kwargs):
    '''
    Creates permissions like syncdb would if we were not using South

    See http://south.aeracode.org/ticket/211
    '''
    from django.db.models import get_app
    from django.contrib.auth.management import create_permissions
    create_permissions(get_app(app), (), 0)

post_migrate.connect(create_permissions_compat)
