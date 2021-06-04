# JetCI
Simple CI that natively operates on Kubernetes.

# CRDs
The JetCI CRDs are used to configure repositories and it also facilitates the build queue.

```
$ kubectl apply -f deploy/crds.yaml
```

An example repository is available in `deploy/repo-example.yaml`. For example of what a JetCI secret might look like, check out `jetci-secret-example.yaml`.

For the operator and webhook to work, a configured service account is provided in `deploy/rbac.yaml`.

# Operator
When new builds are made, the JetCI operator will grab the `.jetci.yaml` from the configured git repository and run those pipelines as pods in the namespace that the repository is configured in.

The replicas can be increased, this controller can handle claiming builds without a leader.

An example deployment is available in `deploy/operator.yaml`.

A build can be manually initiated like so:
```
$ cat <<EOF | kubectl apply -f -
---
apiVersion: future.jetci.xyz/v1alpha1
kind: Build
metadata:
  name: some-build-name-$(openssl rand -hex 4)
spec:
  repository: "some-repo"
  env:
    - name: foo
      value: bar
EOF
```

Deleting a running build will also attempt to delete the pods it generated.

# Webhook Endpoint
This is coming soon. The webhook endpoint will create new builds when requests come in from places like Github.