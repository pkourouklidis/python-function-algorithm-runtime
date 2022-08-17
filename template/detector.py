from scipy import stats

#ksTest detector
def detector(trainSet, liveSet):
    firstFeature = trainSet.axes[1][0]
    pValue = stats.ks_2samp(trainSet[firstFeature].to_list(), liveSet[firstFeature].to_list())[1]
    return int(pValue < 0.05), pValue