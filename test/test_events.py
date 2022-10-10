import pytest
from cloudevents.http import CloudEvent
from cloudevents.conversion import to_structured
from project import create_app


@pytest.fixture
def app():
    return create_app()


def test_random_type(app):
    attributes = {
        "Content-Type": "application/json",
        "source": "from-galaxy-far-far-away",
        "type": "cloudevent.greet.you",
    }

    data = {"name": "john"}

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)

    with app.test_client() as test_client:

        response = test_client.post("/", data=data, headers=headers)
        assert response.status_code == 200


def test_algorithm_create(app):
    attributes = {
        "Content-Type": "application/json",
        "source": "from-galaxy-far-far-away",
        "type": "org.lowcomote.panoptes.baseAlgorithm.create",
    }

    data = {
        "name": "ks_test",
        "codebase": "https://gitlab.betalab.rp.bt.com/betalab/panoptes/examplealgorithmrepo.git",
    }

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)

    with app.test_client() as test_client:

        response = test_client.post("/", data=data, headers=headers)
        assert response.status_code == 200


def test_algorithmExecution_trigger(app):
    attributes = {
        "Content-Type": "application/json",
        "source": "from-galaxy-far-far-away",
        "type": "org.lowcomote.panoptes.baseAlgorithmExecution.trigger",
    }

    data = {
        "modelName": "callcenter",
        "deploymentName": "callFeatures",
        "historicalFeatures": "waitDuration",
        "liveFeatures": "waitDuration",
        "baseAlgorithmExecutionName": "KS_CALLCENTER_WAITDURATION",
        "startDate": "2022-01-01T11:05:13+00:00",
        "algorithmName": "kstest"
    }

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)

    with app.test_client() as test_client:
        response = test_client.post("/", data=data, headers=headers)
        assert response.status_code == 200
