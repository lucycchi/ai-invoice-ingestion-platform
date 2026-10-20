"""The only code that calls the reference API. Every list is fetched page by page until complete."""

from dataclasses import dataclass

import httpx

CATALOG_PAGE_SIZE = 200
LIST_PAGE_SIZE = 100


class ReferenceUnavailable(Exception):
    """The reference API could not be reached, timed out, or answered with a server error."""

    def __init__(self, url: str, detail: str):
        self.url = url
        self.detail = detail
        super().__init__(f"Couldn't reach the reference API at {url}: {detail}")


class ReferenceNotFound(Exception):
    """A sponsor, study or site with this ID isn't in the reference data."""

    def __init__(self, kind: str, id: int):
        self.kind = kind
        self.id = id
        super().__init__(f"{kind.capitalize()} {id} isn't in the reference data.")


@dataclass
class ReferenceData:
    sponsors: list[dict]
    studies: list[dict]
    sites: list[dict]
    study_sites: list[dict]


class ReferenceClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http = http or httpx.Client(timeout=timeout)

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        try:
            response = self.http.get(f"{self.base_url}/api/v1/{path}", params=params, timeout=self.timeout)
        except httpx.HTTPError as err:
            raise ReferenceUnavailable(self.base_url, type(err).__name__) from err
        if response.status_code >= 500:
            raise ReferenceUnavailable(self.base_url, f"HTTP {response.status_code}")
        return response

    def _list(self, path: str, page_size: int, **filters) -> list[dict]:
        items, page = [], 1
        while True:
            params = {k: v for k, v in filters.items() if v is not None} | {"page": page, "page_size": page_size}
            body = self._get(path, params).json()
            items += body["items"]
            if page >= body["pages"]:
                return items
            page += 1

    def _one(self, path: str, kind: str, id: int) -> dict:
        response = self._get(f"{path}/{id}")
        if response.status_code == 404:
            raise ReferenceNotFound(kind, id)
        return response.json()

    def list_sponsors(self) -> list[dict]:
        return self._list("sponsors", LIST_PAGE_SIZE)

    def list_studies(self, sponsor_id: int | None = None) -> list[dict]:
        return self._list("studies", LIST_PAGE_SIZE, sponsor_id=sponsor_id)

    def list_sites(self) -> list[dict]:
        return self._list("sites", LIST_PAGE_SIZE)

    def list_study_sites(self) -> list[dict]:
        return self._list("study-sites", LIST_PAGE_SIZE)

    def list_catalog(self, sponsor_id: int, study_id: int) -> list[dict]:
        return self._list("catalog-items", CATALOG_PAGE_SIZE, sponsor_id=sponsor_id, study_id=study_id)

    def get_sponsor(self, id: int) -> dict:
        return self._one("sponsors", "sponsor", id)

    def get_study(self, id: int) -> dict:
        return self._one("studies", "study", id)

    def get_site(self, id: int) -> dict:
        return self._one("sites", "site", id)


def load_reference_data(client: ReferenceClient) -> ReferenceData:
    """Everything metadata matching needs, in one go."""
    return ReferenceData(
        sponsors=client.list_sponsors(),
        studies=client.list_studies(),
        sites=client.list_sites(),
        study_sites=client.list_study_sites(),
    )
