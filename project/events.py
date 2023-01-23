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


@bp.route("/", methods=["POST"])
def receiveEvent():
    event = from_http(request.headers, request.get_data())
    current_app.logger.info(
        "Received CloudEvent of type %s and data %s", event["type"], event.data
    )
    if event["type"] == "org.lowcomote.panoptes.algorithm.create":
        buildAlgorithm(event.data)
    elif event["type"] == "org.lowcomote.panoptes.baseAlgorithmExecution.trigger":
        triggerExecution(event.data)
    return Response(status=200)


def buildAlgorithm(eventData):
    repoURL = urlparse(eventData["codebase"])
    gitlabToken = os.environ["GITLAB_TOKEN"]
    repo = "https://oath2:" + gitlabToken + "@" + repoURL.netloc + repoURL.path
    id = str(uuid.uuid4())
    git.clone(repo, "/tmp/" + id)
    createRequirements(id)
    packageContext(id)
    storeBuildContext(id)
    launchKanikoBuild(id, eventData["name"])
    cleanup(id)


def createRequirements(id):
    with open("/tmp/" + id + "/requirements.txt", "a") as file:
        # base dependencies
        file.write("\nfeast[aws,postgres]\npandas\ncloudevents\nrequests\n\n")


def packageContext(id):
    tar = tarfile.open("/tmp/" + id + "/" + id + ".tar.gz", "w:gz")
    tar.add("./template/main.py", "main.py")
    tar.add("./template/feature_store.yaml", "feature_store.yaml")
    tar.add("./template/Dockerfile", "Dockerfile")
    tar.add("/tmp/" + id + "/detector.py", "detector.py")
    tar.add("/tmp/" + id + "/requirements.txt", "requirements.txt")
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
            "/kaniko/executor --cache=false --context s3://kaniko/{}.tar.gz --destination=registry.docker.nat.bt.com/panoptes/{}:latest".format(
                id, algorithmName
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
        image="registry.docker.nat.bt.com/panoptes/" + algorithmName + ":latest",
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
