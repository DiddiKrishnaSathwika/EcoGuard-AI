
from datetime import datetime, timezone
import ssl

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from regulation_engine.source_registry import (
    get_all_sources,
    get_source_by_id
)

try:
    import truststore
except ImportError:
    truststore = None


class _SystemTrustAdapter(HTTPAdapter):

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        if truststore is not None:
            pool_kwargs["ssl_context"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        super().init_poolmanager(connections, maxsize, block, **pool_kwargs)


def fetch_source(source):

    url = source["url"]

    result = {
        "source_id": source["source_id"],
        "authority": source["authority"],
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_status": "FAILED",
        "http_status": None,
        "content": "",
        "error_type": None,
        "error": None
    }

    try:
        with requests.Session() as session:
            session.mount("https://", _SystemTrustAdapter())
            response = session.get(
                url,
                timeout=20,
                verify=True,
                headers={
                    "User-Agent": "EcoGuardAI/1.0 (Environmental Research)"
                }
            )

            result["http_status"] = response.status_code
            response.raise_for_status()
            result["final_url"] = response.url

            content_type = response.headers.get("Content-Type", "")

            if "text/html" in content_type.lower():

                soup = BeautifulSoup(response.text, "html.parser")

                for element in soup(["script", "style", "nav", "footer"]):
                    element.decompose()

                content = soup.get_text(separator=" ", strip=True)

                result["page_title"] = (
                    soup.title.get_text(strip=True)
                    if soup.title else "No page title"
                )

            elif "text/" in content_type.lower():

                content = response.text
                result["page_title"] = "Text document"

            else:

                content = ""
                result["page_title"] = (
                    "Non-HTML content. Special extraction required."
                )

            result["content"] = content[:12000]
            result["retrieval_status"] = "HTTP_SUCCESS"

    except requests.exceptions.SSLError as error:
        result["error_type"] = "SSL_ERROR"
        result["error"] = f"TLS certificate verification failed: {error}"
    except requests.exceptions.Timeout as error:
        result["error_type"] = "TIMEOUT"
        result["error"] = f"Connection timed out after 20 seconds: {error}"
    except requests.exceptions.HTTPError as error:
        result["error_type"] = "HTTP_ERROR"
        result["error"] = f"HTTP request failed: {error}"
    except requests.exceptions.ConnectionError as error:
        result["error_type"] = "CONNECTION_ERROR"
        result["error"] = f"Connection failed: {error}"
    except requests.RequestException as error:
        result["error_type"] = "REQUEST_ERROR"
        result["error"] = str(error)

    return result


def retrieve_source_by_id(source_id):

    source = get_source_by_id(source_id)

    if source is None:
        raise ValueError(
            f"Unknown source ID: {source_id}"
        )

    return fetch_source(source)


def retrieve_all_sources():

    sources = get_all_sources()

    results = []

    for source in sources:

        print(
            f"Checking: {source['authority']}..."
        )

        result = fetch_source(source)

        results.append(result)

    return results
