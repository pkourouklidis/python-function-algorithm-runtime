import json
import os
import tarfile
import uuid
from urllib.parse import urlparse

import boto3
from cloudevents.http import from_http
from flask import Blueprint, Response, current_app, request
from kubernetes import client, config
from sh import git, rm

bp = Blueprint("events", __name__)
latestHash = {}

@bp.route("/", methods=["POST"])
def receiveEvent():
    event = from_http(request.headers, request.get_data())
    current_app.logger.info(
        "Received CloudEvent of type %s and data %s", event["type"], event.data
    )
    if event["type"] == "org.lowcomote.panoptes.algorithm.create" and event["subject"] == "pythonFunction":
        buildAlgorithm(event.data, False)
    elif event["type"] == "org.lowcomote.panoptes.algorithm.create" and event["subject"] == "higherOrderPythonFunction":
        buildAlgorithm(event.data, True)
    elif event["type"] == "org.lowcomote.panoptes.baseAlgorithmExecution.trigger":
        triggerExecution(event.data)
    elif event["type"] == "org.lowcomote.panoptes.higherOrderAlgorithmExecution.trigger":
        triggerHOExecution(event.data)
    return Response(status=200)


def buildAlgorithm(eventData, HO):
    algorithmName = eventData["name"]
    repoURL = urlparse(eventData["codebase"])
    gitlabToken = os.environ["GITLAB_TOKEN"]
    repo = "https://oath2:" + gitlabToken + "@" + repoURL.netloc + repoURL.path
    id = str(uuid.uuid4())
    git.clone(repo, "/tmp/" + id)
    commitHash = str(git("--no-pager", "--git-dir", "/tmp/" + id + "/.git", "log", "-n1", '--pretty=format:"%H"')).strip('"')
    current_app.logger.info(commitHash)
    if (latestHash.get(algorithmName, None) != commitHash):
        current_app.logger.info("building image for " + algorithmName)
        latestHash[algorithmName] = commitHash
        createRequirements(id, HO)
        packageContext(id, HO)
        storeBuildContext(id)
        launchKanikoBuild(id, eventData["name"])
        cleanup(id)
    else:
        current_app.logger.info("Already built image for " + algorithmName)

def createRequirements(id, HO):
    with open("/tmp/" + id + "/requirements.txt", "a") as file:
        # base dependencies
        file.write("\ncloudevents\nrequests\n\n")
        if not HO:
            file.write("\nfeast[aws,postgres]\npandas")

def packageContext(id, HO):
    tar = tarfile.open("/tmp/" + id + "/" + id + ".tar.gz", "w:gz")
    templateDir = "./HOtemplate/" if HO else "./template/"
    tar.add(templateDir + "main.py", "main.py")
    tar.add(templateDir + "Dockerfile", "Dockerfile")
    tar.add("/tmp/" + id + "/detector.py", "detector.py")
    tar.add("/tmp/" + id + "/requirements.txt", "requirements.txt")
    if not HO:
        tar.add(templateDir + "feature_store.yaml", "feature_store.yaml")
    tar.close()


def storeBuildContext(id):
    s3 = boto3.Session().resource(
        service_name="s3",
        endpoint_url="http://minio-service.kubeflow.svc.cluster.local:9000",
        aws_access_key_id="minio",
        aws_secret_access_key="minio123",
    )
    s3Object = s3.Object("kaniko", id + ".tar.gz")
    s3Object.put(Body=open("/tmp/" + id + "/" + id + ".tar.gz", "rb"))


def launchKanikoBuild(id, algorithmName):
    envList = [
        {
            "name": "S3_ENDPOINT",
            "value": "http://minio-service.kubeflow.svc.cluster.local:9000",
        },
        {"name": "AWS_ACCESS_KEY_ID", "value": "minio"},
        {"name": "AWS_SECRET_ACCESS_KEY", "value": "minio123"},
        {"name": "AWS_REGION", "value": "us-east-1"},
        {"name": "S3_FORCE_PATH_STYLE", "value": "true"},
    ]

    container = client.V1Container(
        name="kaniko",
        image="registry.docker.nat.bt.com/betalab-build-tools/bt-kaniko-build:latest",
        env=envList,
        volume_mounts=[
            client.V1VolumeMount(name="docker-config", mount_path="/kaniko/.docker")
        ],
        command=[
            "/bin/sh",
            "-c",
            "/kaniko/executor --cache=false --context s3://kaniko/{}.tar.gz --destination=registry.docker.nat.bt.com/panoptes/{}:{}".format(
                id, algorithmName, latestHash[algorithmName]
            ),
        ],
    )

    secretVolume = client.V1SecretVolumeSource(
        secret_name="panoptes-registry-credentials",
        items=[client.V1KeyToPath(key=".dockerconfigjson", path="config.json")],
    )

    podTemplate = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
            volumes=[client.V1Volume(name="docker-config", secret=secretVolume)],
        )
    )

    jobSpec = client.V1JobSpec(
        template=podTemplate, backoff_limit=4, ttl_seconds_after_finished=300
    )

    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name="kaniko-build-" + str(uuid.uuid4())),
        spec=jobSpec,
    )

    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()
    api_response = batch_v1.create_namespaced_job(body=job, namespace="panoptes")

def cleanup(id):
    rm("-rf", "/tmp/" + id)

def triggerExecution(eventData):
    envList = [
        {"name": "modelName", "value": eventData["modelName"]},
        {"name": "deploymentName", "value": eventData["deploymentName"]},
        {"name": "historicalFeatures", "value": eventData["historicalFeatures"]},
        {"name": "liveFeatures", "value": eventData["liveFeatures"]},
        {
            "name": "baseAlgorithmExecutionName",
            "value": eventData["baseAlgorithmExecutionName"],
        },
        {"name": "startDate", "value": eventData["startDate"]},
        {"name": "endDate", "value": eventData["endDate"]},
        {
            "name": "brokerEndpoint",
            "value": "http://broker-ingress.knative-eventing.svc.cluster.local/panoptes/default",
        },
        {
            "name": "FEAST_S3_ENDPOINT_URL",
            "value": "http://minio-service.kubeflow.svc.cluster.local:9000",
        },
        {"name": "AWS_ACCESS_KEY_ID", "value": "minio"},
        {"name": "AWS_SECRET_ACCESS_KEY", "value": "minio123"},
        {"name": "parameters", "value": json.dumps(eventData["parameters"])},
    ]
    algorithmName = eventData["algorithmName"]
    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()
    job = create_job_object(algorithmName, envList)
    api_response = batch_v1.create_namespaced_job(body=job, namespace="panoptes")


def create_job_object(algorithmName, envList):
    # Configureate Pod template container
    container = client.V1Container(
        name="base-algorithm-execution",
        image="registry.docker.nat.bt.com/panoptes/{}:{}".format(algorithmName, latestHash[algorithmName]),
        env=envList,
    )
    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(
            image_pull_secrets=[{"name": "panoptes-registry-credentials"}],
            restart_policy="Never",
            containers=[container],
        )
    )
    # Create the specification of deployment
    spec = client.V1JobSpec(
        template=template, backoff_limit=4, ttl_seconds_after_finished=300
    )
    # Instantiate the job object
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name="python-function-execution-" + str(uuid.uuid4())
        ),
        spec=spec,
    )

    return job

def triggerHOExecution(eventData):
    envList = [
        {"name": "panoptesEndpoint", "value": "panoptes-orchestrator.panoptes.svc.cluster.local"},
        {"name": "observedAlgorithmExecution", "value": eventData["observedAlgorithmExecutionName"]},
        {"name": "count", "value": str(eventData["windowSize"])},
        {"name": "parameters", "value": json.dumps(eventData["parameters"])},
        {"name": "deploymentName", "value": eventData["deploymentName"]},
        {
            "name": "higherOrderAlgorithmExecutionName",
            "value": eventData["higherOrderAlgorithmExecutionName"]
        },
        {"name": "startDate", "value": eventData["startDate"]},
        {"name": "endDate", "value": eventData["endDate"]},
        {
            "name": "brokerEndpoint",
            "value": "http://broker-ingress.knative-eventing.svc.cluster.local/panoptes/default",
        }
    ]

    container = client.V1Container(
        name="higher-order-algorithm-execution",
        image="registry.docker.nat.bt.com/panoptes/" + eventData["higherOrderAlgorithmName"] + ":latest",
        env=envList,
    )
    template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(
            image_pull_secrets=[{"name": "panoptes-registry-credentials"}],
            restart_policy="Never",
            containers=[container],
        )
    )
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name="python-function-execution-" + str(uuid.uuid4())
        ),
        spec = client.V1JobSpec(
        template=template, backoff_limit=4, ttl_seconds_after_finished=300
    )
    )
    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()
    api_response = batch_v1.create_namespaced_job(body=job, namespace="panoptes")