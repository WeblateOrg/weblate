# from : https://github.com/gabrielfalcao/HTTPretty/issues/242
from httpretty import HTTPretty as OriginalHTTPretty
import httpretty
import httpretty.core

try:
    from requests.packages.urllib3.contrib.pyopenssl import (
        inject_into_urllib3, extract_from_urllib3
    )
    pyopenssl_override = True
except ImportError:
    pyopenssl_override = False


class MyHTTPretty(OriginalHTTPretty):
    """ pyopenssl monkey-patches the default ssl_wrap_socket() function in the
    'requests' library, but this can stop the HTTPretty socket monkey-patching
    from working for HTTPS requests.  Our version extends the base HTTPretty
    enable() and disable() implementations to undo and redo the pyopenssl
    monkey-patching, respectively.
    """

    @classmethod
    def enable(cls):
        OriginalHTTPretty.enable()
        if pyopenssl_override:
            # Take out the pyopenssl version - use the default implementation
            extract_from_urllib3()

    @classmethod
    def disable(cls):
        OriginalHTTPretty.disable()
        if pyopenssl_override:
            # Put the pyopenssl version back in place
            inject_into_urllib3()


# Substitute in our version
HTTPretty = MyHTTPretty

httpretty.core.httpretty = MyHTTPretty

# May need to set other module-level attributes here, e.g. enable, reset etc,
# depending on your needs
httpretty.httpretty = MyHTTPretty
httpretty.register_uri = MyHTTPretty.register_uri
httpretty.reset = MyHTTPretty.reset
