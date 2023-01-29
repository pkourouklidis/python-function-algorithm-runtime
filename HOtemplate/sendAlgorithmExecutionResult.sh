curl -v "http://localhost:8080/api/v1/events" -H "Content-Type: application/cloudevents+json"\
 -d '{
    "specversion": "1.0",
    "type": "org.lowcomote.panoptes.baseAlgorithmExecution.result",
    "id": "1", "source": "test",
    "data": {
        "deployment": "callcenter",
        "algorithmExecution": "callcenter-accuracy",
        "level": 1,
        "rawResult": "0.7",
        "startDate": "2022-10-10T17:40:06.449243+00:00",
        "endDate": "2022-10-22T17:40:06.449243+00:00"}}'