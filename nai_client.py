import base64
import json
from os import environ

import dotenv
import requests
from requests.adapters import HTTPAdapter, Retry


IMAGE_URL = "https://image.novelai.net"


def _raise_for_status(response, access_token, image=None):
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        detail = response.text.replace(access_token, "[redacted]")
        if image:
            detail = detail.replace(image, "[image]")
        detail = detail.strip()[:500]
        correlation_id = response.headers.get("x-correlation-id", "unavailable")
        error.args = (f"{error}\nNovelAI response: {detail or '(empty body)'}\nCorrelation ID: {correlation_id}",)
        raise


def _request_target(retry):
    if retry is None or retry <= 1:
        return requests
    retries = Retry(total=retry, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"])
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class NovelAIClient:
    def __init__(self, access_token):
        self.access_token = access_token

    @classmethod
    def from_environment(cls):
        dotenv.load_dotenv()
        token = environ.get("NAI_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("Set NAI_ACCESS_TOKEN in the ComfyUI .env file.")
        return cls(token)

    def encode_vibe(self, image, model, information_extracted, timeout=120):
        request = {"image": "image", "model": model, "information_extracted": information_extracted}
        files = {
            "image": ("blob", base64.b64decode(image), "image/png"),
            "request": ("blob", json.dumps(request), "application/json"),
        }
        response = requests.post(f"{IMAGE_URL}/ai/encode-vibe", files=files, headers=self._headers(), timeout=timeout)
        _raise_for_status(response, self.access_token, image)
        if not response.content:
            raise RuntimeError("NovelAI returned an empty vibe encoding.")
        return base64.b64encode(response.content).decode()

    def generate_image(self, prompt, model, action, parameters, timeout=None, retry=None):
        data = {"input": prompt, "model": model, "action": action, "parameters": parameters}
        request = _request_target(retry)
        try:
            response = request.post(f"{IMAGE_URL}/ai/generate-image", json=data, headers=self._headers(), timeout=timeout)
            _raise_for_status(response, self.access_token)
            return response.content
        finally:
            if isinstance(request, requests.Session):
                request.close()

    def augment_image(self, req_type, width, height, image, options=None, timeout=None, retry=None):
        data = {"req_type": req_type, "width": width, "height": height, "image": image}
        if options:
            data.update(options)
        request = _request_target(retry)
        try:
            response = request.post(f"{IMAGE_URL}/ai/augment-image", json=data, headers=self._headers(), timeout=timeout)
            _raise_for_status(response, self.access_token, image)
            return response.content
        finally:
            if isinstance(request, requests.Session):
                request.close()

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}
