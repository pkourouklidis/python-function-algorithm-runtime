import requests
import os
from detector import detector
import json
import datetime
from cloudevents.http import CloudEvent
from cloudevents.conversion import to_structured

if __name__ == "__main__":
    panoptesEndpoint = os.environ["panoptesEndpoint"]
    observedAlgorithmExecution = os.environ["observedAlgorithmExecution"]
    count = int(os.environ["count"])
    parameters = json.loads(os.environ["parameters"])
    deploymentName = os.environ["deploymentName"]
    executionName = os.environ["higherOrderAlgorithmExecutionName"]
    startDate = datetime.datetime.fromisoformat(
        os.environ["startDate"].replace("Z", "+00:00")
    )
    endDate = datetime.datetime.fromisoformat(
        os.environ["endDate"].replace("Z", "+00:00")
    )
    brokerEndpoint = os.environ["brokerEndpoint"]

    response = requests.get(
        "http://"
        + panoptesEndpoint
        + "/api/v1/algorithmExecutions/"
        + observedAlgorithmExecution,
        params={"count": count},
    )

    level = response.json()["level"]
    raw = response.json()["raw"]

    l, r = detector(level, raw, parameters)
    print(l,r)

    attributes = {
        "source": "runtimes.higherOrderpythonFunction",
        "type": "org.lowcomote.panoptes.higherOrderAlgorithmExecution.result",
    }

    data = {
        "deployment": deploymentName,
        "algorithmExecution": executionName,
        "level": l,
        "rawResult": str(r),
        "startDate": startDate.isoformat(),
        "endDate": endDate.isoformat(),
    }

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)

    print(headers)
    print(data)
    requests.post(brokerEndpoint, data=data, headers=headers)
