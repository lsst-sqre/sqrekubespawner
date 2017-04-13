#!/usr/bin/env python
"""GitHub Organization WhiteList Authenticator

   This class subclasses the oauthenticator.GitHubOAuthentictor class from
   JupyterHub to add a whitelist corresponding to org membership.  We don't
   want this to be the caller's job (as would be normal), because inside
   the authenticator, we're actually authenticated with a GitHub Client ID
   and therefore we don't have to mess around granting access and then
   revoking it as we would if we succeeded and then decided the org
   membership was wrong.

   We use the environment variable GITHUB_ORGANIZATION_WHITELIST to construct
   the whitelist.

   Plus, "ghowl" sounds cool.  Like "ghoul" plus "howl".
"""

import json
import os

from oauthenticator import GitHubOAuthenticator, LocalAuthenticator, \
    GitHubLoginHandler
from tornado import gen, web
from tornado.httputil import url_concat
from tornado.httpclient import HTTPRequest, AsyncHTTPClient, HTTPClient

ghowl = None
ghowlenv = 'GITHUB_ORGANIZATION_WHITELIST'
ghowlstr = os.environ.get(ghowlenv)
if ghowlstr:
    ghowl = ghowlstr.split(',')
# *** Begin duplicated implementation ***
# Support github.com and github enterprise installations
GITHUB_HOST = os.environ.get('GITHUB_HOST') or 'github.com'
if GITHUB_HOST == 'github.com':
    GITHUB_API = 'api.github.com/user'
else:
    GITHUB_API = '%s/api/v3/user' % GITHUB_HOST
# *** End duplicated implementation ***


class GHOWLLoginHandler(GitHubLoginHandler):
    """Must be able to get organization membership.
    """
    scope = ["read:org"]


class GHOWLAuthenticator(GitHubOAuthenticator):
    """This is just GitHubOAuthenticator with an environment-derived
    whitelist added.  GITHUB_ORGANIZATION_WHITELIST is taken to be a
    comma-separated list of GitHub organizations.  When
    authenticating, we do the GitHub auth first, and then when
    authenticated as the user, we get the list of organizations it's
    in.  If any of those arguments are in GITHUB_ORGANIZATION_WHITELIST
    then we return the user name; otherwise, we return None.

    """

    login_handler = GHOWLLoginHandler

    # It's a Tornado coroutine
    @gen.coroutine
    def authenticate(self, handler, data=None):
        """Standard GitHub OAuth, only with an org membership check.
        """
        self.log.info("Authenticating GHOWL.")
        if not ghowl:
            # Why on earth would you call this class without the org list?
            #  Just use the (standard) GitHubOAuthenticator instead.
            self.log.warning("No GitHub Organization WhiteList defined.")
            return None  # NOQA
        # We are duplicating the superclass implementation because we need the
        #  access token, which is not exposed by the parent implementation.
        self.log.info("Entering GH OAuth duplicated section")
        # *** Begin duplicated implementation ***
        code = handler.get_argument("code", False)
        if not code:
            raise web.HTTPError(400, "oauth callback made without a token")
        # TODO: Configure the curl_httpclient for tornado
        http_client = AsyncHTTPClient()

        # Exchange the OAuth code for a GitHub Access Token
        #
        # See: https://developer.github.com/v3/oauth/

        # GitHub specifies a POST request yet requires URL parameters
        params = dict(
            client_id=self.client_id,
            client_secret=self.client_secret,
            code=code
        )

        url = url_concat("https://%s/login/oauth/access_token" % GITHUB_HOST,
                         params)

        req = HTTPRequest(url,
                          method="POST",
                          headers={"Accept": "application/json"},
                          body=''  # Body is required for a POST...
                          )

        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))

        access_token = resp_json['access_token']

        # Determine who the logged in user is
        headers = {"Accept": "application/json",
                   "User-Agent": "JupyterHub",
                   "Authorization": "token {}".format(access_token)
                   }
        req = HTTPRequest("https://%s" % GITHUB_API,
                          method="GET",
                          headers=headers
                          )
        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))
        # *** End duplicated implementation ***
        self.log.info("Exiting GH OAuth duplicated section")
        user = resp_json["login"]
        self.log.info("Got GH user %s." % user)
        orgurl = "https://%s/orgs" % GITHUB_API
        self.log.info("About to request URL %s" % orgurl)
        orgreq = HTTPRequest(orgurl,
                             method="GET",
                             headers=headers
                             )
        orghttp_client = HTTPClient()  # Synchronous: we have to get orgs
        orgresp = orghttp_client.fetch(orgreq)
        orgresp_json = json.loads(orgresp.body.decode('utf8', 'replace'))
        orghttp_client.close()
        orglist = [item["login"] for item in orgresp_json]
        self.log.info("User %s Orgs: %s" % (user, str(orglist)))
        intersection = [org for org in orglist if org in ghowl]
        self.log.info("Intersected Orgs: %s" % str(intersection))
        if not intersection:
            # Sorry, buddy.  You're not on the list.  You're NOBODY.
            self.log.warning("User %s is not in %r" % (user, ghowl))
            user = None
        return user  # NOQA


class LocalGHOWLAuthenticator(LocalAuthenticator, GHOWLAuthenticator):
    """A version that mixes in local system user creation"""
    pass
