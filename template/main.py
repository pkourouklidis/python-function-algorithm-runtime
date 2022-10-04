import datetime
import os

# import pandas as pd
from feast import FeatureStore, FileSource
from pytz import utc

from detector import detector
from cloudevents.http import CloudEvent, to_structured 
import requests


def getHistoricalData(modelName, store, historicalFeatures):
    historicalData = store.get_saved_dataset(modelName + "_training").to_df()
    return historicalData[historicalFeatures]


def getLiveData(deploymentName, store, liveFeatures, startDate):
    fv = store.get_feature_view(deploymentName)
    liveData = None
    source = fv.batch_source
    if type(source) == FileSource:
        from feast.infra.offline_stores.file import FileOfflineStore

        joinKeys = [
            item
            for sublist in [store.get_entity(x).join_keys for x in fv.entities]
            for item in sublist
        ]
        liveData = FileOfflineStore.pull_all_from_table_or_query(
            config=store.config,
            data_source=source,
            join_key_columns=joinKeys,
            timestamp_field=source.timestamp_field,
            feature_name_columns=liveFeatures,
            start_date=startDate,
            end_date=datetime.datetime.now(tz=utc),
        ).to_df()
    return liveData[liveFeatures]


if __name__ == "__main__":
    modelName = os.environ["modelName"]
    deploymentName = os.environ["deploymentName"]
    historicalFeatures = os.environ["historicalFeatures"].split(",")
    liveFeatures = os.environ["liveFeatures"].split(",")
    executionName = os.environ["baseAlgorithmExecutionName"]
    brokerEndpoint = os.environ["brokerEndpoint"]
    startDate = datetime.datetime().fromisoformat(os.environ["liveFeaturesStartDate"])
    store = FeatureStore(repo_path=".")
    historicalData = None
    if len(historicalFeatures) > 0:
        historicalData = getHistoricalData(modelName, store, historicalFeatures)
    liveData = None
    if len(liveFeatures) > 0:
        liveData = getLiveData(deploymentName, store, liveFeatures, startDate)
    level, raw = detector(historicalData, liveData)
    print(historicalData)
    print(liveData)
    print(level, raw)

    attributes = {
    "source": "runtimes.pythonFunction",
    "type": "org.lowcomote.panoptes.baseAlgorithmExecution.result",
    }
    
    data = {"deployment": deploymentName, "algorithmExecution": executionName, "level": level, "rawResult": raw, "date": datetime.datetime.now(tz=utc)}

    event = CloudEvent(attributes, data)
    headers, data = to_structured(event)
    
    print(headers)
    print(data)
    requests.post(brokerEndpoint, data = data, headers=headers)
