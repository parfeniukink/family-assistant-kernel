from dataclasses import dataclass, field


@dataclass
class ArticleCandidate:
    title: str
    description: str
    url: str
    extra_urls: list[str] = field(default_factory=list)

    @property
    def all_urls(self) -> list[str]:
        return [self.url] + self.extra_urls
