from trends.domain.models import Article

from .dedupe import title_similarity


def cluster_articles(articles: list[Article], threshold: float = 0.62) -> list[list[Article]]:
    """Build deterministic connected components from title similarity."""
    parent = list(range(len(articles)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(articles):
        for right_index in range(left_index + 1, len(articles)):
            right = articles[right_index]
            if title_similarity(left, right) >= threshold:
                union(left_index, right_index)

    groups: dict[int, list[Article]] = {}
    for index, article in enumerate(articles):
        groups.setdefault(find(index), []).append(article)
    return sorted(
        groups.values(),
        key=lambda group: max((item.published_at or item.collected_at) for item in group),
        reverse=True,
    )

