# sqrekubespawner

SQuaRE edition of jupyterhub-kubespawner.  Uses the GitHub userid as the
UID, if we have it (which means, if we used the GHOWL authenticator to
log in)

## Installation

sqrekubespawner runs on Python 3.3 or greater. You can install it with

```bash
pip install sqrekubespawner
```

This will also install the dependency: `jupyterhub-kubespawner`.

## Example usage

Your `jupyterhub_config.py` file should contain
`c.JupyterHub.spawner_class = 'sqrekubespawner.SQREKubeSpawner`.

It otherwise behaves identically to the KubeSpawner spawner class.

