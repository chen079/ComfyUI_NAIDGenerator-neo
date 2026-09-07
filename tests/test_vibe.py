import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

import requests
import torch
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("naid_test")
package.__path__ = [str(ROOT)]
comfy = types.ModuleType("comfy")
comfy.utils = types.ModuleType("comfy.utils")
comfy.utils.common_upscale = lambda samples, w, h, method, crop: torch.nn.functional.interpolate(samples, size=(h, w), mode=method, align_corners=False)
folder_paths = Mock()
with patch.dict(sys.modules, {"naid_test": package, "comfy": comfy, "comfy.utils": comfy.utils, "folder_paths": folder_paths}):
    for name in ("utils", "nodes"):
        spec = importlib.util.spec_from_file_location(f"naid_test.{name}", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    nodes = sys.modules["naid_test.nodes"]
    utils = sys.modules["naid_test.utils"]


class VibeTests(unittest.TestCase):
    def setUp(self):
        self.image = torch.zeros((1, 32, 48, 3))
        self.model = "nai-diffusion-4-5-full"
        self.encoding = b"\x00\xffencoded-vibe\x80"
        self.vibe = {"model": self.model, "encoding": base64.b64encode(self.encoding).decode()}
        self.token = patch.object(nodes, "get_access_token", return_value="test-token")
        self.token.start()
        self.addCleanup(self.token.stop)
        # Every HTTP request is mocked, including unexpected ones.
        self.post = patch.object(requests, "post", side_effect=AssertionError("Unexpected HTTP request"))
        self.http = self.post.start()
        self.addCleanup(self.post.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        folder_paths.get_output_directory.return_value = self.directory.name
        folder_paths.get_save_image_path.return_value = (self.directory.name, "test", 1, "", "test")
        png = io.BytesIO()
        Image.new("RGB", (64, 64)).save(png, format="PNG")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("image.png", png.getvalue())
        self.generated = Mock(content=archive.getvalue())

    def generate(self, option=None, seed=123):
        return nodes.GenerateNAID().generate(False, 64, 64, "test", "", 28, 5.0, False, False, "none", "k_euler", "native", seed, 1.0, 0.0, True, option)

    def test_encode_to_generation_and_reuse(self):
        self.http.side_effect = [Mock(content=self.encoding), self.generated, self.generated]
        vibe, = nodes.EncodeVibe().encode(self.image, self.model, 0.7, 180)
        request = self.http.call_args.kwargs
        self.assertEqual(request["headers"], {"Authorization": "Bearer test-token"})
        self.assertEqual(request["timeout"], 180)
        self.assertNotIn("json", request)
        payload = json.loads(request["files"]["request"][1])
        self.assertEqual(payload, {"image": "image", "model": self.model, "information_extracted": 0.7})
        self.assertEqual(request["files"]["request"][2], "application/json")
        self.assertEqual(request["files"]["image"][2], "image/png")
        prepared = requests.Request("POST", "https://image.novelai.net/ai/encode-vibe", files=request["files"], headers=request["headers"]).prepare()
        self.assertTrue(prepared.headers["Content-Type"].startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="request"', prepared.body)
        self.assertIn(b'name="image"', prepared.body)
        reference = Image.open(io.BytesIO(request["files"]["image"][1]))
        self.assertEqual(reference.size, (48, 32))
        self.assertEqual(vibe, self.vibe)
        for strength in (0.6, 0.3):
            option, = nodes.VibeTransferOption().set_option(strength=strength, encoded_vibe=vibe)
            image, = self.generate(option, seed=int(strength * 100))
            self.assertEqual(tuple(image.shape), (1, 64, 64, 3))
            data = self.http.call_args.kwargs["json"]
            self.assertEqual(data["model"], self.model)
            self.assertEqual(data["parameters"]["reference_image_multiple"], [vibe["encoding"]])
            self.assertEqual(data["parameters"]["reference_strength_multiple"], [strength])
            self.assertNotIn("reference_information_extracted_multiple", data["parameters"])
        self.assertEqual([call.args[0].rsplit("/", 1)[-1] for call in self.http.call_args_list], ["encode-vibe", "generate-image", "generate-image"])

    def test_multiple_vibes_preserve_upstream_options(self):
        first, = nodes.VibeTransferOption().set_option(strength=0.4, encoded_vibe=self.vibe)
        second, = nodes.VibeTransferOption().set_option(strength=0.2, encoded_vibe=self.vibe, option=first)
        self.assertEqual(len(first["encoded_vibe"]), 1)
        self.http.side_effect = None
        self.http.return_value = self.generated
        self.generate(second)
        params = self.http.call_args.kwargs["json"]["parameters"]
        self.assertEqual(params["reference_strength_multiple"], [0.4, 0.2])
        self.assertEqual(params["reference_image_multiple"], [self.vibe["encoding"]] * 2)

    def test_model_mismatch_before_or_after_transfer(self):
        with self.assertRaisesRegex(ValueError, "model must match"):
            nodes.VibeTransferOption().set_option(encoded_vibe=self.vibe, option={"model": "nai-diffusion-3"})
        option, = nodes.VibeTransferOption().set_option(encoded_vibe=self.vibe)
        option, = nodes.ModelOption().set_option("nai-diffusion-4-full", option)
        with self.assertRaisesRegex(ValueError, "model must match"):
            self.generate(option)
        self.http.assert_not_called()

    def test_raw_v3_still_works_and_v4_explains_encoding(self):
        option, = nodes.VibeTransferOption().set_option(self.image, 0.8, 0.6)
        with self.assertRaisesRegex(ValueError, "requires EncodeVibe"):
            self.generate(option)
        self.http.assert_not_called()
        option, = nodes.ModelOption().set_option("nai-diffusion-3", option)
        self.http.side_effect = None
        self.http.return_value = self.generated
        self.generate(option)
        params = self.http.call_args.kwargs["json"]["parameters"]
        self.assertEqual(params["reference_information_extracted_multiple"], [0.8])
        self.assertTrue(base64.b64decode(params["reference_image_multiple"][0]).startswith(b"\x89PNG"))

    def test_missing_or_ambiguous_inputs(self):
        with self.assertRaisesRegex(ValueError, "Connect an image"):
            nodes.VibeTransferOption().set_option()
        with self.assertRaisesRegex(ValueError, "not both"):
            nodes.VibeTransferOption().set_option(image=self.image, encoded_vibe=self.vibe)
        with self.assertRaisesRegex(ValueError, "one image"):
            nodes.EncodeVibe().encode(self.image.repeat(2, 1, 1, 1), self.model, 1.0, 120)
        self.http.assert_not_called()

    def test_encoding_errors_are_not_retried_or_cached(self):
        response = requests.Response()
        response.status_code = 500
        response._content = b'{"statusCode":500,"message":"Invalid reference image"}'
        response.headers["x-correlation-id"] = "abc123"
        self.http.side_effect = None
        self.http.return_value = response
        with self.assertRaisesRegex(requests.HTTPError, "Invalid reference image") as raised:
            nodes.EncodeVibe().encode(self.image, self.model, 1.0, 120)
        self.assertIs(raised.exception.response, response)
        self.assertIn("abc123", str(raised.exception))
        self.http.assert_called_once()
        self.http.return_value = Mock(content=b"")
        with self.assertRaisesRegex(RuntimeError, "empty vibe"):
            nodes.EncodeVibe().encode(self.image, self.model, 1.0, 120)

    def test_encoding_error_details_are_bounded_and_redacted(self):
        response = requests.Response()
        response.status_code = 502
        image = utils.image_to_base64(self.image)
        response._content = f"test-token {image} upstream error ".encode() + b"x" * 2000
        self.http.side_effect = None
        self.http.return_value = response
        with self.assertRaises(requests.HTTPError) as raised:
            nodes.EncodeVibe().encode(self.image, self.model, 1.0, 120)
        message = str(raised.exception)
        self.assertNotIn("test-token", message)
        self.assertNotIn(image, message)
        self.assertIn("upstream error", message)
        self.assertLess(len(message), 800)

    def test_tls_failure_is_not_retried(self):
        self.http.side_effect = requests.exceptions.SSLError("TLS handshake interrupted")
        with self.assertRaises(requests.exceptions.SSLError):
            nodes.EncodeVibe().encode(self.image, self.model, 1.0, 120)
        self.http.assert_called_once()
        self.assertNotIn("verify", self.http.call_args.kwargs)

    def test_disconnected_encoding_is_not_retried(self):
        self.http.side_effect = requests.ConnectionError("Remote end closed connection without response")
        with self.assertRaises(requests.ConnectionError):
            nodes.EncodeVibe().encode(self.image, self.model, 1.0, 120)
        self.http.assert_called_once()

    def test_unconnected_generation_is_unchanged(self):
        self.http.side_effect = None
        self.http.return_value = self.generated
        self.generate()
        data = self.http.call_args.kwargs["json"]
        self.assertEqual(data["model"], self.model)
        self.assertEqual(data["parameters"]["reference_image_multiple"], [])


if __name__ == "__main__":
    unittest.main()
