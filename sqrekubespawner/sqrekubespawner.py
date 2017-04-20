#!/usr/bin/env python
import json
import string
from kubespawner import KubeSpawner
from tornado import gen


class SQREKubeSpawner(KubeSpawner):
    """Use GitHub ID as UID, if we have one"""

    def _expand_user_properties(self, template):
        """Plug in UID from GitHub, which we will have stashed in
        auth_context, if we're using our GHOWLAuth class.
        """
        # Make sure username matches the restrictions for DNS labels
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_username = ''.join(
            [s if s in safe_chars else '-' for s in self.user.name.lower()])
        userid = self.user.id
        try:
            userid = self.user.authenticator.auth_context["uid"]
        except (NameError, AttributeError) as err:
            self.log.info("User did not have a UID in auth context: ",
                          str(err))
        return template.format(
            userid=userid,
            username=safe_username
        )

    @gen.coroutine
    def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        podspec = yield super(SQREKubeSpawner, self).get_pod_manifest()
        # Patch in GH ID and Access Token
        try:
            gh_id = self.user.authenticator.auth_context["uid"]
            gh_token = self.user.authenticator.auth_context["access_token"]
            env = podspec["spec"]["containers"][0]["env"]
            env.append({"name": "GITHUB_ID",
                        "value": str(gh_id)})
            env.append({"name": "GITHUB_ACCESS_TOKEN",
                        "value": gh_token})
        except (AttributeError, NameError) as err:
            self.log.info("Could not attach GH ID and access token: %s",
                          str(err))
        self.log.info("Pod spec: %s", json.dumps(podspec, sort_keys=True,
                                                 indent=4))
        return podspec  # NoQA
