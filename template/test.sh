#/bin/bash
export FEAST_S3_ENDPOINT_URL="http://localhost:9000"
export AWS_ACCESS_KEY_ID="minio"
export AWS_SECRET_ACCESS_KEY="minio123"
export modelName="callcenter"
export deploymentName="callFeatures"
export historicalFeatures="waitDuration"
export liveFeatures="waitDuration"
export baseAlgorithmExecutionName="KS_CALLCENTER_WAITDURATION"
export brokerEndpoint="http://localhost:9500/"

python ./main.py