"""Embedding values with the model identity required for meaningful comparison."""
import math


class EmbeddingVector(list):
    def __init__(self, values, model):
        super().__init__(float(value) for value in values)
        if not self or not all(math.isfinite(value) for value in self) or not any(self):
            raise ValueError("Embedding must be a finite, nonzero vector")
        if not model:
            raise ValueError("Embedding model identity is required")
        self.model = str(model)
