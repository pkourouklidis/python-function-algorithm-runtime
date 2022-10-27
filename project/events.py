from flask import request, Response, current_app, Blueprint
from cloudevents.http import from_http
from sh import git
from sh import rm
from zipfile import ZipFile
import base64
import requests
import uuid
from kubernetes import client, config


bp = Blueprint("events", __name__)


@bp.route("/", methods=["POST"])
def receiveEvent():
    event = from_http(request.headers, request.get_data())
    current_app.logger.info(
        "Received CloudEvent of type %s and data %s", event["type"], event.data
    )
    if event["type"] == "org.lowcomote.panoptes.baseAlgorithm.create":
        buildAlgorithm(event.data)
    elif event["type"] == "org.lowcomote.panoptes.baseAlgorithmExecution.trigger":
        triggerExecution(event.data)
    return Response(status=200)


def buildAlgorithm(eventData):
    repo = eventData["codebase"]
    tempdir = "/tmp/" + str(uuid.uuid4())
    git.clone(repo, tempdir)
    descriptor = createDescriptor(eventData["name"], tempdir)
    packageDetector(descriptor, tempdir)
    with open(tempdir + "/zipFile", "rb") as file:
        # base64 encode the zipfile and then turn it into text for json
        payload = base64.b64encode(file.read()).decode("utf-8")
        url = "http://unstable-gateway.rp.bt.com/function/deploy-application"
        requestBody = {"action": "deploy", "value": payload}
        r = requests.post(url, json=requestBody)
        current_app.logger.info(r.text)
        # print(r.text, flush=True)
    rm("-rf", tempdir)


def createDescriptor(name, tempdir):
    descriptor = ""
    # name of the image
    descriptor += "applicationName: " + name + "\n\n"
    # language information
    descriptor += "language: python\nversion: 3.9\n\n"
    # python dependencies
    descriptor += "pythonDependencies:\n"
    # user dependencies
    with open(tempdir + "/requirements.txt", "r") as file:
        for line in file:
            descriptor += "  - " + line + "\n"
    # base dependencies
    descriptor += "  - feast[aws,postgres]\n  - pandas\n  - cloudevents\n  - requests\n\n"

    # additional information
    descriptor += "requiresWebserver: none\nrunCommand: python main.py"
    return descriptor


def packageDetector(descriptor, tempdir):
    zipObj = ZipFile(tempdir + "/zipFile", "w")
    zipObj.writestr("deployment-desc.yml", descriptor)
    zipObj.write("./template/main.py", "main.py")
    zipObj.write("./template/feature_store.yaml", "feature_store.yaml")
    zipObj.write(tempdir + "/detector.py", "detector.py")
    zipObj.close()


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
        image="registry.docker.nat.bt.com/vulcanapplications/"
        + algorithmName
        + "-application:latest",
        env=envList,
    )
    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(
            image_pull_secrets=[{"name": "vulcan-registry-credentials"}],
            restart_policy="Never",
            containers=[container],
        )
    )
    # Create the specification of deployment
    spec = client.V1JobSpec(template=template, backoff_limit=4, ttl_seconds_after_finished=300)
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
