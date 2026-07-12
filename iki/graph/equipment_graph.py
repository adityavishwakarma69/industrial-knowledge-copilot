from collections import defaultdict
from typing import Dict, List
from ..models import Chunk

class EquipmentGraph:
    def __init__(self):
        self.tag_to_chunks: Dict[str, List[Chunk]] = defaultdict(list)
        self.tag_to_doc_types: Dict[str, set] = defaultdict(set)

    def build(self, chunks: List[Chunk]) -> None:
        self.tag_to_chunks.clear()
        self.tag_to_doc_types.clear()
        for chunk in chunks:
            tags = chunk.metadata.get("equipment_tags", [])
            for tag in tags:
                self.tag_to_chunks[tag].append(chunk)
                self.tag_to_doc_types[tag].add(chunk.doc_type.value)

    def neighbors(self, tag: str) -> List[Chunk]:
        return self.tag_to_chunks.get(tag, [])

    def related_tags(self, tag: str) -> set:
        """Find other equipment tags that co-occur with this one in the same chunks."""
        related = set()
        for chunk in self.neighbors(tag):
            for other_tag in chunk.metadata.get("equipment_tags", []):
                if other_tag != tag:
                    related.add(other_tag)
        return related

    def summary(self, tag: str) -> dict:
        chunks = self.neighbors(tag)
        return {
            "tag": tag,
            "mention_count": len(chunks),
            "doc_types": sorted(self.tag_to_doc_types.get(tag, [])),
            "related_tags": sorted(self.related_tags(tag)),
        }