# JetCI
Simple CI that natively operates on Kubernetes.

# Operator
When new builds are made, the JetCI operator will grab the `.jetci.yaml` from the configured git repository and run those pipelines as pods in the namespace that the repository is configured in. The file `example.jetci.yaml` is an example of `.jetci.yaml` features.

The replicas can be increased, this controller can handle claiming builds without a leader.

An example deployment is available in `deploy/operator.yaml`.

Here's a quick install:
```
$ kubectl create ns jetci
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/crds.yaml
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/rbac.yaml
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/operator.yaml
```

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