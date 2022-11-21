import datetime
import json
import os

import requests
from cloudevents.http import CloudEvent, to_structured
from detector import detector
from feast import FeatureStore, FileSource
from feast.infra.offline_stores.contrib.postgres_offline_store.postgres_source import (
    PostgreSQLSource,
)


def getHistoricalData(modelName, store, historicalFeatures):
    historicalData = store.get_saved_dataset(modelName + "_training").to_df()
    return historicalData[historicalFeatures]


def getLiveData(deploymentName, store, liveFeatures, startDate, endDate):
    fv = store.get_feature_view(deploymentName)
    liveData = None
    source = fv.batch_source
    if type(source) == FileSource:
        from feast.infra.offline_stores.file import FileOfflineStore

        offlineStoreClass = FileOfflineStore
    elif type(source) == PostgreSQLSource:
        from feast.infra.offline_stores.contrib.postgres_offline_store.postgres import (
            PostgreSQLOfflineStore,
        )

        offlineStoreClass = PostgreSQLOfflineStore

    liveData = offlineStoreClass.pull_all_from_table_or_query(
        config=store.config,
        data_source=source,
        join_key_columns=fv.join_keys,
        timestamp_field=source.timestamp_field,
        feature_name_columns=liveFeatures,
        start_date=startDate,
        end_date=endDate,
    ).to_df()

    return liveData[liveFeatures]


if __name__ == "__main__":
    modelName = os.environ["modelName"]
    deploymentName = os.environ["deploymentName"]
    historicalFeatures = os.environ["historicalFeatures"].split(",")
    liveFeatures = os.environ["liveFeatures"].split(",")
    executionName = os.environ["baseAlgorithmExecutionName"]
    brokerEndpoint = os.environ["brokerEndpoint"]
    startDate = datetime.datetime.fromisoformat(
        os.environ["startDate"].replace("Z", "+00:00")
    )
    endDate = datetime.datetime.fromisoformat(
        os.environ["endDate"].replace("Z", "+00:00")
    )
    store = FeatureStore(repo_path=".")
    parameters = json.loads(os.environ["parameters"])
    historicalData = None
    if len(historicalFeatures) > 0:
        historicalData = getHistoricalData(modelName, store, historicalFeatures)
    liveData = None
    if len(liveFeatures) > 0:
        liveData = getLiveData(deploymentName, store, liveFeatures, startDate, endDate)
    level, raw = detector(historicalData, liveData, parameters)
    print(historicalData)
    print(liveData)
    print(level, raw)

    attributes = {
        "source": "runtimes.pythonFunction",
        "type": "org.lowcomote.panoptes.baseAlgorithmExecution.result",
    }

    data = {
        "deployment": deploymentName,
        "algorithmExecution": executionName,
        "level": level,
        "rawResult": str(raw),
        "startDate": startDate.isoformat(),
        "endDate": endDate.isoformat(),
    }

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)

    print(headers)
    print(data)
    requests.post(brokerEndpoint, data=data, headers=headers)
