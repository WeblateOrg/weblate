Selenium key fixtures
=====================

These keys are intentionally invalid and must stay that way.

The Selenium documentation screenshots only need key-looking text to exercise
the UI layout. The fixtures are display-only sample data, not generated
credentials and not suitable for SSH or GPG use. Keeping them invalid avoids
the risk of someone copying them from screenshots or test data and using them
for a real deployment.

The SSH public keys keep the usual OpenSSH line shape, but their base64 payload
does not describe a valid SSH public key blob. The GPG fixture keeps the usual
ASCII-armored block shape, but is not a usable public key export.
