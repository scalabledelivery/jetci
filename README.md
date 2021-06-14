# JetCI (Archived)
This repository is now archived. It was pretty cool to work on this, it's a very primitive example of making an operator that takes input and does work in a cloud native way with Python.

The reason this is archived is because Cloud Native CI is already solved. Viktor Farcic has a really good video that [quickly compares Argo vs Tekton](https://www.youtube.com/watch?v=dAUpAq7hfeA).

Instead of being an all-in-one solution, ArgoCD provides 3 components that enable good pipelines.
https://github.com/argoproj/argo-cd
https://github.com/argoproj/argo-workflows
https://github.com/argoproj/argo-events

Also there's Tekton: https://tekton.dev

~~Simple CI that natively operates on Kubernetes.~~

# Operator
When new builds are made, the JetCI operator will grab the `.jetci.yaml` from the configured git repository and run those pipelines as pods in the namespace that the repository is configured in. The file `example.jetci.yaml` is an example of `.jetci.yaml` features.

The replicas can be increased, this controller can handle claiming builds without a leader.

An example deployment is available in `deploy/operator.yaml`.

Here's a quick install:
```
$ kubectl create ns jetci
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/crds.yaml
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/operator-rbac.yaml
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
This provides an endpoint for automating build entries. From places like Github for example.

`apiToken` is required to be set in the repository. The URL path looks like this:
```
/run_build?namespace=default&repository=some-repo&auth_token=pretty-random-token-here-thanks
```

Quick install:
```
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/webhook-endpoint-rbac.yaml
$ kubectl -n jetci apply -f https://raw.githubusercontent.com/scalabledelivery/jetci/master/deploy/webhook-endpoint.yaml
```

## How to Expose the Endpoint
In `deploy/`, there is a service example and an example of using traefik to expose the endpoint.
