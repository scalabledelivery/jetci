#!/usr/bin/env python3
from flask import Flask, request
from kubernetes import client, config
import secrets
import base64
import json

# API Information for custom resources
API_VERSION = "v1alpha1"
API_GROUP   = "future.jetci.xyz"

try:
    config.load_kube_config()
except:
    # load_kube_config throws if there is no config, but does not document what it throws, so I can't rely on any particular type here
    config.load_incluster_config()

def create_build(repo, env):
    build_name = repo['metadata']['name'] + "-" + secrets.token_hex(4)

    build_obj = {
        "apiVersion": API_GROUP + "/" + API_VERSION,
        "kind": "Build",
        "metadata": {
            "name": build_name
        },
        "spec": {
            "repository": repo['metadata']['name'],
            "env": env
        }
    }

    try:
        build_obj = client.CustomObjectsApi().create_namespaced_custom_object(API_GROUP, API_VERSION, repo['metadata']['namespace'], "builds", build_obj)
    except:
        print("failed to create build for repo:", repo['metadata']['namespace'], repo['metadata']['name'])
        return { "status": "failed", "name": build_name, "message": "failed to create build" }
    
    print("created new build:", repo['metadata']['namespace'], build_name)

    return { "status": "success", "name": build_name, "message": "created build: " + build_name }

# TODO: Consolidate into shared.py
def get_repo(namespace, reponame):
    try:
        repo = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "repositories", reponame)
    except:
        print("repo not found:", namespace, reponame)
        return False
    return repo


def get_api_token(repo):
    # Neet to get the actual API token from secrets
    try:
        jetci_conf = client.CoreV1Api().read_namespaced_secret(repo['spec']['apiToken']['secretName'], repo['metadata']['namespace'])
    except:
        print("secret not found for repo:", repo['metadata']['namespace'], repo['metadata']['name'], repo['spec']['apiToken']['secretName'])
        return False

    if repo['spec']['apiToken']['secretKeyPath'] not in jetci_conf.data:
        print("secret key not found for repo:", repo['metadata']['namespace'], repo['metadata']['name'], repo['spec']['apiToken']['secretKeyPath'])
        return False

    # repo.spec.apiToken.secretKeyPath
    api_token = base64.standard_b64decode(jetci_conf.data[repo['spec']['apiToken']['secretKeyPath']]).decode('utf-8')
    return api_token


app = Flask(__name__)


@app.route("/run_build")
def run_build():
    namespace = request.args.get('namespace')
    repo_name = request.args.get('repository')
    auth_token = request.args.get('auth_token')
    # TODO: Pull env stuff from POST data?

    # Get the repo
    repo = get_repo(namespace, repo_name)

    # Bad repo requested
    if repo == False:
        print("Repo not found", namespace, repo_name)
        return "not authorized", 403

    # Get the API token.
    api_token = get_api_token(repo)

    # Someone didn't set an API Token or the token provided wasn't correct.
    if api_token != auth_token:
        print("Provided API Token is invalid", namespace, repo_name)
        return "not authorized", 403

    env = []

    if request.method == 'POST':
        for col in request.form.keys():
            env.append({
                    "name": "WEBHOOK_" + str(col).replace('-', '_'),
                    "value": request.form[col]
                })

    return json.dumps(create_build(repo, env))


app.run(host='0.0.0.0', port=80)