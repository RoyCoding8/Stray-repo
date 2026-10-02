def ENTRY(task, oracle, max_queries=16):
    return reduce_software(task, oracle, method="ddmin", max_queries=max_queries)