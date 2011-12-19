# -*- coding: utf-8 -*-

"""
requests.auth
~~~~~~~~~~~~~

This module contains the authentication handlers for Requests.
"""

import time
import hashlib

from base64 import b64encode
from urlparse import urlparse

from .utils import randombytes, parse_dict_header



def _basic_auth_str(username, password):
    """Returns a Basic Auth string."""
    return 'Basic %s' % b64encode('%s:%s' % (username, password))


class AuthBase(object):
    """Base class that all auth implementations derive from"""

    def __call__(self, r):
        raise NotImplementedError('Auth hooks must be callable.')


class HTTPBasicAuth(AuthBase):
    """Attaches HTTP Basic Authentication to the given Request object."""
    def __init__(self, username, password):
        self.username = str(username)
        self.password = str(password)

    def __call__(self, r):
        r.headers['Authorization'] = _basic_auth_str(self.username, self.password)
        return r


class HTTPProxyAuth(HTTPBasicAuth):
    """Attaches HTTP Proxy Authenetication to a given Request object."""
    def __call__(self, r):
        r.headers['Proxy-Authorization'] = _basic_auth_str(self.username, self.password)
        return r


class HTTPDigestAuth(AuthBase):
    """Attaches HTTP Digest Authentication to the given Request object."""
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def handle_401(self, r):
        """Takes the given response and tries digest-auth, if needed."""

        s_auth = r.headers.get('www-authenticate', '')

        if 'digest' in s_auth.lower():

            last_nonce = ''
            nonce_count = 0

            chal = parse_dict_header(s_auth.replace('Digest ', ''))

            realm = chal['realm']
            nonce = chal['nonce']
            qop = chal.get('qop')
            algorithm = chal.get('algorithm', 'MD5')
            opaque = chal.get('opaque', None)

            algorithm = algorithm.upper()
            # lambdas assume digest modules are imported at the top level
            if algorithm == 'MD5':
                H = lambda x: hashlib.md5(x).hexdigest()
            elif algorithm == 'SHA':
                H = lambda x: hashlib.sha1(x).hexdigest()
            # XXX MD5-sess
            KD = lambda s, d: H("%s:%s" % (s, d))

            if H is None:
                return None

            # XXX not implemented yet
            entdig = None
            p_parsed = urlparse(r.request.url)
            path = p_parsed.path + p_parsed.query

            A1 = "%s:%s:%s" % (self.username, realm, self.password)
            A2 = "%s:%s" % (r.request.method, path)

            if qop == 'auth':
                if nonce == last_nonce:
                    nonce_count += 1
                else:
                    nonce_count = 1
                    last_nonce = nonce

                ncvalue = '%08x' % nonce_count
                cnonce = (hashlib.sha1("%s:%s:%s:%s" % (
                    nonce_count, nonce, time.ctime(), randombytes(8)))
                    .hexdigest()[:16]
                )
                noncebit = "%s:%s:%s:%s:%s" % (nonce, ncvalue, cnonce, qop, H(A2))
                respdig = KD(H(A1), noncebit)
            elif qop is None:
                respdig = KD(H(A1), "%s:%s" % (nonce, H(A2)))
            else:
                # XXX handle auth-int.
                return None

            # XXX should the partial digests be encoded too?
            base = 'username="%s", realm="%s", nonce="%s", uri="%s", ' \
                   'response="%s"' % (self.username, realm, nonce, path, respdig)
            if opaque:
                base += ', opaque="%s"' % opaque
            if entdig:
                base += ', digest="%s"' % entdig
            base += ', algorithm="%s"' % algorithm
            if qop:
                base += ', qop=auth, nc=%s, cnonce="%s"' % (ncvalue, cnonce)

            r.request.headers['Authorization'] = 'Digest %s' % (base)
            r.request.send(anyway=True)
            _r = r.request.response
            _r.history.append(r)

            return _r

        return r

    def __call__(self, r):
        r.hooks['response'] = self.handle_401
        return r
