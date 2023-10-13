import faiss


class Metric:
    """
    which metric the model use
    """
    COS = 'COS'
    L1 = 'L1'
    L2 = 'L2'
    Linf = 'Linf'
    Lp = 'Lp'
    Canberra = 'Canberra'
    BrayCurtis = 'BrayCurtis'
    JensenShannon = 'JensenShannon'
    INNER_PRODUCT = 'INNER_PRODUCT'


# faiss supports 8 metrics
METRIC_TO_FAISS = {
    Metric.COS: faiss.METRIC_INNER_PRODUCT,
    Metric.INNER_PRODUCT: faiss.METRIC_INNER_PRODUCT,
    Metric.L1: faiss.METRIC_L1,
    Metric.L2: faiss.METRIC_L2,
    Metric.Linf: faiss.METRIC_Linf,
    Metric.Lp: faiss.METRIC_Lp,
    Metric.Canberra: faiss.METRIC_Canberra,
    Metric.BrayCurtis: faiss.METRIC_BrayCurtis,
    Metric.JensenShannon: faiss.METRIC_JensenShannon,
}
