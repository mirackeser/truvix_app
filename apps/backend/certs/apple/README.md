# Apple root certificates

Place Apple's root certificate here, for example `AppleRootCA-G3.cer`, taken
from <https://www.apple.com/certificateauthority/>.

It is committed rather than downloaded at startup on purpose. This certificate
is the entire basis for trusting a purchase: fetching it at runtime would mean
that whoever could answer the request could decide what counts as a valid
subscription. Verifying its SHA-256 fingerprint against Apple's published value
before committing it is worth the minute it takes.

Any file here ending in `.cer`, `.der`, `.pem` or `.crt` is loaded and treated
as a trusted root, so this directory should hold nothing else.

Without a certificate here the subscription endpoints answer `503` and grant
nothing — refusing is the only safe response to being unable to check.
