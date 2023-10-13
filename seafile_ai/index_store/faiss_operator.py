# -*- coding: utf-8 -*-
import faiss


class FaissOperator:

    def index_factory(self, d, index_type, metric):
        return faiss.index_factory(d, index_type, metric)

    def normalize_L2(self, embeddings):
        faiss.normalize_L2(embeddings)

    def write_index(self, index, index_path):
        faiss.write_index(index, index_path)

    def read_index(self, index_path):
        return faiss.read_index(index_path)

faiss_operator = FaissOperator()
