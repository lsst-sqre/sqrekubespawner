#!/usr/bin/env python
import string
from kubespawner import KubeSpawner
from tornado import gen


def make_pod_spec(
    name,
    image_spec,
    image_pull_policy,
    image_pull_secret,
    port,
    cmd,
    run_as_uid,
    fs_gid,
    env,
    volumes,
    volume_mounts,
    labels,
    cpu_limit,
    cpu_guarantee,
    mem_limit,
    mem_guarantee
):
    """
    Make a k8s pod specification for running a user notebook.
    Parameters:
      - name:
        Name of pod. Must be unique within the namespace the object is
        going to be created in. Must be a valid DNS label.
      - image_spec:
        Image specification - usually a image name and tag in the form
        of image_name:tag. Same thing you would use with docker commandline
        arguments
      - image_pull_policy:
        Image pull policy - one of 'Always', 'IfNotPresent' or 'Never'. Decides
        when kubernetes will check for a newer version of image and pull it
        when running a pod.
      - image_pull_secret:
        Image pull secret - Default is None -- set to your secret name to pull
        from private docker registry.
      - port:
        Port the notebook server is going to be listening on
      - cmd:
        The command used to execute the singleuser server.
      - run_as_uid:
        The UID used to run single-user pods. The default is to run as the user
        specified in the Dockerfile, if this is set to None.
      - fs_gid
        The gid that will own any fresh volumes mounted into this pod, if using
        volume types that support this (such as GCE). This should be a group
        that the uid the process is running as should be a member of, so that
        it can read / write to the volumes mounted.
      - env:
        Dictionary of environment variables.
      - volumes:
        List of dictionaries containing the volumes of various types this pod
        will be using. See k8s documentation about volumes on how to specify
        these
      - volume_mounts:
        List of dictionaries mapping paths in the container and the volume(
        specified in volumes) that should be mounted on them. See the k8s
        documentaiton for more details
      - labels:
        Labels to add to the spawned pod.
      - cpu_limit:
        Float specifying the max number of CPU cores the user's pod is
        allowed to use.
      - cpu_guarantee:
        Float specifying the max number of CPU cores the user's pod is
        guaranteed to have access to, by the scheduler.
      - mem_limit:
        String specifying the max amount of RAM the user's pod is allowed
        to use. String instead of float/int since common suffixes are allowed
      - mem_guarantee:
        String specifying the max amount of RAM the user's pod is guaranteed
        to have access to. String ins loat/int since common suffixes
        are allowed
    """
    pod_security_context = {}
    if run_as_uid is not None:
        pod_security_context['runAsUser'] = int(run_as_uid)
    if fs_gid is not None:
        pod_security_context['fsGroup'] = int(fs_gid)
    image_secret = []
    if image_pull_secret is not None:
        image_secret = [{"name": image_pull_secret}]
    print("Podspec arguments:\nname: ", name)
    print("  sec context: ", str(pod_security_context))
    print("  image_secret: ", str(image_secret))
    print("  image: ", str(image_spec))
    print("  args: ", cmd)
    print("  port:", str(port))
    podspec = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
            'labels': labels,
        },
        'spec': {
            'securityContext': pod_security_context,
            "imagePullSecrets": image_secret,
            'containers': [
                {
                    'name': 'notebook',
                    'image': image_spec,
                    'args': cmd,
                    'imagePullPolicy': image_pull_policy,
                    'ports': [{
                        'containerPort': port,
                    }],
                    'resources': {
                        'requests': {
                            # If these are None, it's ok. the k8s API
                            # seems to interpret that as 'no limit',
                            # which is what we want.
                            'memory': mem_guarantee,
                            'cpu': cpu_guarantee,
                        },
                        'limits': {
                            'memory': mem_limit,
                            'cpu': cpu_limit,
                        }
                    },
                    'env': [
                        {'name': k, 'value': v}
                        for k, v in env.items()
                    ],
                    'volumeMounts': volume_mounts
                }
            ],
            'volumes': volumes
        }
    }
    return podspec


class SQREKubeSpawner(KubeSpawner):
    """Use GitHub ID as UID, if we have one"""

    def _expand_user_properties(self, template):
        # Make sure username matches the restrictions for DNS labels
        safe_chars = set(string.ascii_lowercase + string.digits)
        safe_username = ''.join(
            [s if s in safe_chars else '-' for s in self.user.name.lower()])
        userid = self.user.id
        try:
            userid = self.user.authenticator.auth_context["uid"]
        except NameError as err:
            self.log.info("User did not have a UID in auth context.")

        return template.format(
            userid=userid,
            username=safe_username
        )

    @gen.coroutine
    def get_pod_manifest(self):
        """
        Make a pod manifest that will spawn current user's notebook pod.
        """
        # Add a hack to ensure that no service accounts are mounted in spawned
        #  pods
        # This makes sure that we don't accidentally give access to the whole
        # kubernetes API to the users in the spawned pods.
        # See
        # https://github.com/kubernetes/kubernetes/issues/16779#\
        #    issuecomment-157460294
        hack_volumes = [{
            'name': 'no-api-access-please',
            'emptyDir': {}
        }]
        hack_volume_mounts = [{
            'name': 'no-api-access-please',
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount',
            'readOnly': True
        }]
        if callable(self.singleuser_uid):
            singleuser_uid = yield gen.maybe_future(self.singleuser_uid(self))
        else:
            singleuser_uid = self.singleuser_uid

        if callable(self.singleuser_fs_gid):
            singleuser_fs_gid = yield gen.maybe_future(self.singleuser_fs_gid(self))
        else:
            singleuser_fs_gid = self.singleuser_fs_gid

        if self.cmd:
            real_cmd = self.cmd + self.get_args()
        else:
            real_cmd = None

        psp = make_pod_spec(
            self.pod_name,
            self.singleuser_image_spec,
            self.singleuser_image_pull_policy,
            self.singleuser_image_pull_secrets,
            self.port,
            real_cmd,
            singleuser_uid,
            singleuser_fs_gid,
            self.get_env(),
            self._expand_all(self.volumes) + hack_volumes,
            self._expand_all(self.volume_mounts) + hack_volume_mounts,
            self.singleuser_extra_labels,
            self.cpu_limit,
            self.cpu_guarantee,
            self.mem_limit,
            self.mem_guarantee,
        )
        self.log.info("Real_cmd: %s" % real_cmd)
        return psp
