from django.conf import settings
from django.contrib.auth.models import User
import ldap

class LdapModelBackend():
    def authenticate(self, username=None, password=None):
	try:
	    ldap_client = ldap.initialize(settings.LDAP_URI)
	    ldap_client.simple_bind_s('uid='+username+','+settings.LDAP_BASE_DN, password)
	except:
	    user = None
	else:
	    try:
		user = User.objects.get(username=username)
	    except User.DoesNotExist:
		user = User.objects.create_user(username=username,password=password)
	    else:
		user.set_password(password)
		user.save()
	return user

    def get_user(self, user_id):
	try:
	    return User.objects.get(pk=user_id)
	except User.DoesNotExist:
	    return None
