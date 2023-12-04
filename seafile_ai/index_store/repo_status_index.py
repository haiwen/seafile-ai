
class RepoStatus(object):
    def __init__(self, repo_id, from_commit, to_commit):
        self.repo_id = repo_id
        self.from_commit = from_commit
        self.to_commit = to_commit

    def need_recovery(self):
        return self.to_commit is not None


class RepoStatusIndex(object):
    """The repo-head index is used to store the status for each repo.

    For each repo:
    (1) before update: commit = <previously indexed commit>, updatingto = None
    (2) during updating: commit = <previously indexed commit>, updatingto = <current latest commit>
    (3) after updating: commit = <newly indexed commit>, updatingto = None

    When error occured during updating, the status is left in case (2). So the
    next time we update that repo, we can recover the failed process again.

    The elasticsearch document id for each repo in repo_head index is its repo
    id.
    """

    index_name = 'repo_head'
    mapping = {
        'properties': {
            'repo_id': {
                'type': 'keyword'
            },
            'commit_id': {
                'type': 'keyword'
            }
            ,
            'updatingto': {
                'type': 'keyword'
            }
        },
    }

    def __init__(self, seasearch_api):
        self.seasearch_api = seasearch_api
        self.create_index_if_missing()

    def create_index_if_missing(self):
        if not self.seasearch_api.check_index_mapping(self.index_name).get('is_exist'):
            self.seasearch_api.create_mapping(self.index_name, self.mapping)

    def check_repo_status(self, repo_id):
        return self.seasearch_api.check_document_by_id(self.index_name, repo_id).get('is_exist')

    def add_repo_status(self, repo_id, commit_id, updatingto):
        date = {
            'repo_id': repo_id,
            'commit_id': commit_id,
            'updatingto': updatingto,
        }
        doc_id = repo_id
        self.seasearch_api.create_document_by_id(self.index_name, doc_id, date)

    def begin_update_repo(self, repo_id, old_commit_id, new_commit_id):
        self.add_repo_status(repo_id, old_commit_id, new_commit_id)

    def finish_update_repo(self, repo_id, commit_id):
        self.add_repo_status(repo_id, commit_id, None)

    def delete_repo_status_by_id(self, repo_id):
        return self.seasearch_api.delete_document_by_id(self.index_name, repo_id)

    def get_repo_status_by_id(self, repo_id):
        doc = self.seasearch_api.get_document_by_id(self.index_name, repo_id)
        if doc.get('error'):
            return None
        commit_id = doc['_source']['commit_id']
        updatingto = doc['_source']['updatingto']
        repo_id = doc['_source']['repo_id']

        return RepoStatus(repo_id, commit_id, updatingto)

    def update_repo_status_by_id(self, doc_id, data):
        self.seasearch_api.update_document_by_id(self.index_name, doc_id, data)

    def get_repo_status_by_time(self, check_time):
        per_size = 200
        start = 0
        repo_head_list = []
        while True:
            query_params = {
                "query": {
                    "bool": {
                        "must": [
                            {"range":
                                {"@timestamp":
                                    {
                                        "lt": check_time
                                    }
                                }
                            }
                        ]
                    }
                },
                "_source": ["commit_id", "updatingto"],
                "from": start,
                "size": per_size,
                "sort": ["-@timestamp"],
            }

            result = self.seasearch_api.normal_search(self.index_name, query_params)
            total = result['hits']['total']['value']
            hits = result['hits']['hits']

            for hit in hits:
                repo_id = hit['_id']
                commit_id = hit.get('_source').get('commit_id')
                updatingto = hit.get('_source').get('updatingto')
                repo_head_list.append({'repo_id': repo_id, 'commit_id': commit_id, 'updatingto': updatingto})

            start += per_size
            if len(hits) < per_size or start == total:
                return repo_head_list
