#!/usr/bin/env python3
from kubernetes import client, config, watch
from kubernetes.stream import stream
from kubernetes.stream.ws_client import ERROR_CHANNEL
import secrets
import socket
import time
import json
import threading
import yaml

# API Information for custom resources
API_VERSION = "v1alpha1"
API_GROUP   = "future.jetci.xyz"

try:
    config.load_kube_config()
except:
    # load_kube_config throws if there is no config, but does not document what it throws, so I can't rely on any particular type here
    config.load_incluster_config()

# TODO: Update this to an array of locks. I'm doing things this way because it should result in less mistakes in prototyping.
# Something to help prevent pipeline threads from modifying the same build at the same time.
run_locker = threading.Lock()

def container_logging(namespace, build_name, pipeline_name, pod_name, container_name):
    for log_entry in watch.Watch().stream(client.CoreV1Api().read_namespaced_pod_log, pod_name, namespace, container=container_name, follow=True, _preload_content=False):
        build_log(namespace, build_name, pipeline_name, container_name, "-", log_entry, "-")
    

def execute_pipeline(namespace, build_name, pipeline_specification):
    # Generate the pod name
    pod_name = build_name +  "-" + pipeline_specification['name'] + "-" + secrets.token_hex(4) # Max length is 253 characters

    # Add this pod to the build
    add_pod_to_build(namespace, build_name, pod_name)


    # We take the specification and convert it to pod_info for k8s.
    # To simplify this. here is a base object
    pod_info = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "app.kubernetes.io/managed-by": "kubed-ci-runner",
            "name": pod_name
        },
        "spec": {
            "containers": [],
            "volumes": [
                # We need somewhere for 
                # See https://kubernetes.io/docs/concepts/storage/volumes/#emptydir
                {
                    "name": "source-dir",
                    "emptyDir": {}
                }
            ]
        }

    }

    # Add volumes from pipeline to the pod
    if 'volumes' in pipeline_specification:
        for volume in pipeline_specification['volumes']:
            pod_info['spec']['volumes'].append(volume)
        
    # Iterate the containers in the specification and add them to pod_info
    for container_specification in pipeline_specification['containers']:
        # We use a container template to expand upon for readability
        container = {
                "name": container_specification['name'],
                "image": container_specification['image'],
                "workingDir": "/usr/src",
                "volumeMounts": [
                    {
                        "name": "source-dir",
                        "mountPath": "/usr/src"
                    }
                ],
                "imagePullPolicy": "Always",
                'env': [],
                "restartPolicy": "Never",
                "securityContext": {}
        }


        # Add readinessProbes
        if 'readinessProbe' in container_specification:
            container['readinessProbe'] = container_specification['readinessProbe']

        # TODO: Need some rules engine to make it so that this isn't allowed by default.
        if 'privileged' in container_specification and container_specification['privileged'] == True:
            container['securityContext']['privileged'] = True

        if 'volumeMounts' in container_specification:
            for volume_mount in container_specification['volumeMounts']:
                container['volumeMounts'].append(volume_mount)

        # Overwrite the entry point if requested
        if 'entrypoint' in container_specification:
            container["command"] = container_specification['entrypoint']

        # Need to gather a simple version of the env.        
        # We start with an empty env
        container_env = {}
        
        # Write the repo env

        # Write the build env over last env

        # Write the conainer specification env over last env
        if 'env' in container_specification:
            for env_var in container_specification['env']:
                container_env[env_var['name']] = env_var

        # Now add the consolidated environment to the container env.
        for k in container_env.keys():
            container['env'].append(container_env[k])

        pod_info['spec']['containers'].append(container)

        # TODO: debug output.
        #print("---------- final pipeline pod -----------")
        #print(yaml.dump(pod_info))
        #print("---------- final pipeline pod /end-------")




    # Create the pod in kubernetes
    try:
        resp = client.CoreV1Api().create_namespaced_pod(body=pod_info, namespace=namespace)
    except client.exceptions.ApiException as err:
        print("Failed to create pod:", pod_name, ":", err)
        return False

    # Wait for pod to be ready
    while True:
        resp = client.CoreV1Api().read_namespaced_pod(name=pod_name, namespace=namespace)
        
        if resp.status.phase != 'Pending':

            all_ready = True

            # Iterate the container ready statuses.
            for cstat in resp.status.container_statuses:
                if cstat.ready == False:
                    all_ready = False # Still not ready

            if all_ready and resp.status.phase != 'Running':
                print("Expected", pod_name, "to be in the running phase, but it's phase is ", resp.status.phase)
                return False
            
            if all_ready and resp.status.phase == 'Running':
                break

        time.sleep(1)


    # Pod is ready, run commands in the containers
    for container_specification in pipeline_specification['containers']:
        if 'commands' not in container_specification:
            container_specification['commands'] = []
        
        # capture container output
        threading.Thread(target=container_logging, args=[namespace, build_name, pipeline_specification['name'], pod_name, container_specification['name']]).start()

        for command in container_specification['commands']:
            # Exec command in container.
            res = pod_exec(namespace, pod_name, container_specification['name'], command)

            # Human readable status.
            if res['status'] == 0:
                status = 'success'
            else:
                status = 'failed'

            # Update the build log.
            entry_status = build_log(namespace, build_name, pipeline_specification['name'], container_specification['name'], command, res['output'], status)
            if entry_status == False:
                print("Unable to update build:", namespace, build_name)
                print("Stopping pipeline", pipeline_specification['name'])
                return

            # Break from this pipeline if it failed.
            if res['status'] != 0:
                break

    client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)


def execute_pipelines(namespace, build_name, pipelines):
    # Iterate and run each pipeline in an array of pipelines.
    for pipeline in pipelines:
        # TODO: Add git-clone-repo task to pipeline.
        #build_and_execute_pipeline(namespace, pod_base_name, pipeline)
        threading.Thread(target=execute_pipeline, args=[namespace, build_name, pipeline]).start()
    
    threading.Thread(target=build_loop, args=[namespace, build_name]).start()





def add_pod_to_build(namespace, build_name, pod_name):
    run_locker.acquire()
    print("Adding pod to build:", namespace, build_name, pod_name)
    try:
        build_obj = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name)
    except client.exceptions.ApiException as err:
        print("add_pod_to_build(): Failed to get build:", namespace, build_name)
        print(err)
        run_locker.release()
        return

    build_obj['pods'].append(pod_name)

    try:
        client.CustomObjectsApi().patch_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name, build_obj)
    except client.exceptions.ApiException as err:
        print("Failed add pod to build:", namespace, build_name)
        print(err)
        run_locker.release()
        return

    run_locker.release()





def build_loop(namespace, build_name):
    # Update the build status
    set_build_status(namespace, build_name, "Running")

    while True:
        # Get pods in build
        try:
            build_obj = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name)
        except client.exceptions.ApiException as err:
            print("build_loop(): Failed to get build:", namespace, build_name)
            print(err)
            return
        
        # Pod detection
        pods_remaining = 0
        for pod_name in build_obj['pods']:
            try:
                resp = client.CoreV1Api().read_namespaced_pod(name=pod_name, namespace=namespace)
            except: # happens when pod doesn't exist anymore
                continue
            
            if resp.status.phase == 'Pending' or resp.status.phase == 'Running':
                pods_remaining += 1
        
        if pods_remaining == 0:
            set_build_status(namespace, build_name, "Complete")
            return
        
        time.sleep(5)
        



def set_build_status(namespace, build_name, status):
    run_locker.acquire()
    try:
        build_obj = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name)
    except client.exceptions.ApiException as err:
        print("set_build_status(): Failed to get build:", namespace, build_name)
        print(err)
        run_locker.release()
        return

    build_obj['status'] = status

    try:
        client.CustomObjectsApi().patch_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name, build_obj)
    except client.exceptions.ApiException as err:
        print("Failed to change status of build:", namespace, build_name)
        print(err)
        run_locker.release()
        return
    run_locker.release()


def build_log(namespace, build_name, pipeline_name, container_name, command, output, status):
    # TODO: Debug flags.
    #print("build_log():")
    #print("namespace", namespace)
    #print("build_name", build_name)
    #print("pipeline_name", pipeline_name)
    #print("command", command)
    #print("output:")
    #print()
    #print(output)
    #print("status", status)
    #print("-----")

    run_locker.acquire()
    try:
        build_obj = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name)
        build_obj['logs'].append({
            'pipelineName': pipeline_name,
            'command': str(command),
            'output': output,
            'container': container_name,
            'status': status
        })
    except client.exceptions.ApiException as err:
        print("build_log(): Failed to get build:", namespace, build_name)
        print(err)
        run_locker.release()
        return False
    
    try:
        client.CustomObjectsApi().patch_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "builds", build_name, build_obj)
    except client.exceptions.ApiException as err:
        print("Failed to update build:", namespace, build_name)
        print(err)
        run_locker.release()
        return False

    run_locker.release()
    return True


# TODO: Consolidate into shared.py
def get_repo(namespace, reponame):
    try:
        repo = client.CustomObjectsApi().get_namespaced_custom_object(API_GROUP, API_VERSION, namespace, "repositories", reponame)
    except:
        print("repo not found:", namespace, reponame)
        return False
    return repo



def get_jetci_yaml(namespace, repo):    
    # This pod is going to be used to get .jetci.yaml
    pod_name = "git-jetci-yaml-" + secrets.token_hex(4)
    pod_info = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "app.kubernetes.io/managed-by": "jetci-operator",
            "name": pod_name
        },
        "spec": {
            "containers": [
                {
                    "name": "git-jetci-yaml",
                    "image": "alpine/git:latest",
                    "command": [ "/bin/sh", "-c", "while true; do sleep 300s; done" ],
                    "workingDir": "/usr/src",
                    "volumeMounts": [],
                    "imagePullPolicy": "Always",
                    "env":[
                        { "name": "GIT_SSH_COMMAND", "value": "ssh -o StrictHostKeyChecking=no" }
                    ],
                    "restartPolicy": "Never"
                }
            ],
            "volumes": []
        }
    }

    # Add ssh key to container
    if repo['spec']['authType'] == "ssh":
        # Add the volume
        pod_info["spec"]["volumes"].append({
            "name": "git-ssh-key",
            "secret": {
                "secretName": repo['spec']['sshKey']['secretName'],
                "defaultMode": yaml.safe_load('0400') # TODO: 0400 becomes 256 in yaml? There's probably a data type for this.
            },
        })

        # Add to the container's volume mounts
        pod_info["spec"]["containers"][0]['volumeMounts'].append({
            "name": "git-ssh-key",
            "mountPath": "/root/.ssh/id_rsa",
            "subPath": repo['spec']['sshKey']['secretKeyPath'],
            "readOnly": True,
        })

    try:
        resp = client.CoreV1Api().create_namespaced_pod(body=pod_info, namespace=namespace)
    except client.exceptions.ApiException as err:
        print("Failed to create pod:", pod_name, ":", err)
        return False

    # Wait for pod to be ready.
    while True:
        resp = client.CoreV1Api().read_namespaced_pod(name=pod_name, namespace=namespace)
        if resp.status.phase != 'Pending':
            if resp.status.phase != 'Running':
                print("Expected", pod_name, "to be in the running phase, but it's phase is ", resp.status.phase)
                return False
            break
        time.sleep(1)

    res = pod_exec(namespace, pod_name, "git-jetci-yaml", "git init")
    if res['status'] != 0:
        print("get_jetci_yaml(): failed: git init")
        print(res)
        client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)
        return False

    res = pod_exec(namespace, pod_name, "git-jetci-yaml", "git remote add origin -f " + repo['spec']["repoPath"]) # https://github.com/scalabledelivery/resolve-host-patcher.git
    if res['status'] != 0:
        print("get_jetci_yaml(): failed: git remote add origin -f " + repo['spec']["repoPath"])
        print(res)
        client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)
        return False

    res = pod_exec(namespace, pod_name, "git-jetci-yaml", "git checkout origin/" + repo['spec']["repoBranch"] + " -- .jetci.yaml")
    if res['status'] != 0:
        print("Failed to fetch .jetci.yaml from ", repo['metadata']['name'], ":", repo['spec']["repoPath"])
        print(res)
        client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)
        return False

    res = pod_exec(namespace, pod_name, "git-jetci-yaml", "cat .jetci.yaml")
    if res['status'] != 0:
        print("Failed to read .jetci.yaml from ", repo['metadata']['name'], ":", repo['spec']["repoPath"])
        print(res)
        client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)
        return False

    client.CoreV1Api().delete_namespaced_pod(pod_name, namespace)
    return res['output']





# Executes commands inside of containers
def pod_exec(namespace, pod_name, container, command):
    if not isinstance(command, list):
        command = command.split()

    resp = stream(client.CoreV1Api().connect_get_namespaced_pod_exec, pod_name, namespace, container=container,  command=command, stderr=True, stdin=True, stdout=True, tty=False, _preload_content=False)

    stderr = ""
    stdout = ""
    combinedout = ""

    while resp.is_open():
        # This was taken from resp.read_all()
        # read_all consumes the ERROR_CHANNEL
        # We just want to combine outputs, but 
        # consume specific output later
        combinedout += resp._all.getvalue()
        resp._all = resp._all.__class__()

        # Now we consume output
        stderr += resp.read_stderr()
        stdout += resp.read_stdout()
    

    return {
        'output': combinedout,
        'stdout': stdout,
        'stderr': stderr,
        'status': resp.returncode
    }


# This is the event loop.
def operator_loop():
    for event in watch.Watch().stream(client.CustomObjectsApi().list_cluster_custom_object, API_GROUP, API_VERSION, "builds", resource_version=""):
        if event["type"] == "DELETED":
            for pod_name in event['object']['pods']:
                try:
                    client.CoreV1Api().delete_namespaced_pod(pod_name, event['object']['metadata']['namespace'])
                except:
                    continue

        if event["type"] == "ADDED" and event['object']["claimedBy"] == "":
            event['object']['claimedBy'] = socket.getfqdn()
            try:
                client.CustomObjectsApi().patch_namespaced_custom_object(API_GROUP, API_VERSION, event['object']['metadata']['namespace'], "builds", event['object']['metadata']['name'], event['object'])
            except client.exceptions.ApiException:
                continue

            print("Claimed build:", event['object']['claimedBy'], ":", event['object']['metadata']['namespace'], event['object']['metadata']['name'])

            # Load the repo configuration
            repo = get_repo(event['object']['metadata']['namespace'], event['object']['spec']['repository'])

            # Get the contents of .jetci.yaml
            jetci_obj = get_jetci_yaml(repo['metadata']['namespace'], repo)

            if jetci_obj == False:
                print("get_jetci_yaml() returned false.")
                build_log(event['object']['metadata']['namespace'], event['object']['metadata']['name'], '@jetci', '@jetci', "@jetci-log", "Failed to pull .jetci.yaml", "failed")
                set_build_status(event['object']['metadata']['namespace'], event['object']['metadata']['name'], "Failed")

            else:
                # TODO: Need to lint.
                try:
                    jetci_obj = yaml.safe_load(jetci_obj)
                except:
                    print("Error loading contents from .jetci.yaml")
                    set_build_status(event['object']['metadata']['namespace'], event['object']['metadata']['name'], "Failed")
                    continue

                # Pipeline convenience doctor
                for i in range(len(jetci_obj['pipelines'])):
                    # Ensure that volumes is set.
                    if 'volumes' not in jetci_obj['pipelines'][i]:
                        jetci_obj['pipelines'][i]['volumes'] = []

                    # Build the repo cloning pod
                    clone_git_repository = {
                        "name": "clone-git-repository",
                        "image": "alpine/git:latest",
                        "entrypoint": [ "/bin/sh", "-c", "sleep 86000s" ],
                        "env":[
                            { "name": "GIT_SSH_COMMAND", "value": "ssh -o StrictHostKeyChecking=no" }
                        ],
                        "commands":
                            [
                                "git init",
                                "git remote add origin -f " + repo['spec']["repoPath"],
                                "git checkout origin/" + repo['spec']["repoBranch"] + " -- README.md"
                            ],
                    }

                    # Inject repo ssh-key mount data into the pipeline
                    if repo['spec']['authType'] == "ssh":
                        jetci_obj['pipelines'][i]['volumes'].append({
                                    "name": "git-ssh-key",
                                    "secret": {
                                        "secretName": repo['spec']['sshKey']['secretName'],
                                        "defaultMode": yaml.safe_load('0400') # TODO: 0400 becomes 256 in yaml? There's probably a data type for this.
                                    },
                                })

                        clone_git_repository['volumeMounts'] = [
                            {
                                "name": "git-ssh-key",
                                "mountPath": "/root/.ssh/id_rsa",
                                "subPath": repo['spec']['sshKey']['secretKeyPath'],
                                "readOnly": True,
                            }
                        ]

                    # Inject the clone-git-repository pod into the pipeline.
                    jetci_obj['pipelines'][i]['containers'].insert(0, clone_git_repository)

                # Run the pipelines.
                execute_pipelines(event['object']['metadata']['namespace'], event['object']['metadata']['name'], jetci_obj['pipelines'])

operator_loop()
