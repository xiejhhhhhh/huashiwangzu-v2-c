import asyncio
import base64
import hashlib
import hmac
import logging
import os
import time
import uuid

import httpx

from .base import GenResult, GenSpec, ImageProvider

logger = logging.getLogger("v2.image-gen").getChild("liblib")


class LiblibProvider(ImageProvider):
    provider_key = "liblib"

    async def generate(self, spec: GenSpec) -> list[GenResult]:
        cfg = spec.template_config
        api_base = cfg["api_base"].rstrip("/")
        text2img_path = cfg["text2img_path"]
        status_path = cfg["status_path"]
        template_uuid = cfg["template_uuid"]
        access_key = self._resolve_env(cfg["access_key_env"])
        secret_key = self._resolve_env(cfg["secret_key_env"])
        poll_max = int(cfg.get("poll_max", 60))
        poll_interval = float(cfg.get("poll_interval_sec", 5))

        if not access_key or not secret_key:
            raise RuntimeError(f"LiblibAI credentials not configured ({cfg['access_key_env']}/{cfg['secret_key_env']})")

        gen_params = {
            "prompt": spec.prompt,
            "imgCount": spec.count,
            "steps": spec.steps,
        }
        aspect_ratio = self._resolve_aspect_ratio(spec)
        if aspect_ratio:
            gen_params["aspectRatio"] = aspect_ratio
        else:
            gen_params["imageSize"] = {"width": spec.width, "height": spec.height}

        body = {
            "templateUuid": template_uuid,
            "generateParams": gen_params,
        }

        signed_uri = self._sign(text2img_path, access_key, secret_key)
        url = f"{api_base}{signed_uri}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            logger.info("LiblibAI submitting text2img: prompt=%r", spec.prompt[:80])
            resp = await client.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"LiblibAI text2img failed: code={data.get('code')} msg={data.get('msg', data.get('message', ''))}")

        generate_uuid = data["data"]["generateUuid"]

        result_data = await self._poll_status(
            api_base, status_path, access_key, secret_key,
            generate_uuid, poll_max, poll_interval,
        )

        images: list[GenResult] = []
        for img_info in result_data.get("images", []):
            image_url = img_info.get("imageUrl", "")
            seed = img_info.get("seed")
            if image_url:
                images.append(GenResult(
                    image_url=image_url,
                    seed=seed,
                    meta={"placeholder": False},
                ))

        points_cost = result_data.get("pointsCost")
        account_balance = result_data.get("accountBalance")
        if images and (points_cost is not None or account_balance is not None):
            images[0].meta["points_cost"] = points_cost
            images[0].meta["balance"] = account_balance

        logger.info(
            "LiblibAI generated %d images, cost=%s, balance=%s",
            len(images), points_cost, account_balance,
        )
        return images

    async def _poll_status(
        self, api_base: str, status_path: str,
        access_key: str, secret_key: str,
        generate_uuid: str, poll_max: int, poll_interval: float,
    ) -> dict:
        body = {"generateUuid": generate_uuid}
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            for attempt in range(poll_max):
                await asyncio.sleep(poll_interval)
                signed_uri = self._sign(status_path, access_key, secret_key)
                url = f"{api_base}{signed_uri}"
                try:
                    resp = await client.post(
                        url,
                        json=body,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("LiblibAI poll attempt %d/%d failed: %s", attempt + 1, poll_max, e)
                    continue

                if data.get("code") != 0:
                    raise RuntimeError(f"LiblibAI status error: code={data.get('code')} msg={data.get('msg', data.get('message', ''))}")

                gen_status = data.get("data", {}).get("generateStatus", 0)
                if gen_status == 5:
                    return data.get("data", {})
                if gen_status in (6, 7):
                    msg = data.get("data", {}).get("generateMsg", "unknown error")
                    raise RuntimeError(f"LiblibAI generation failed: status={gen_status} msg={msg}")

                logger.debug("LiblibAI poll attempt %d/%d: status=%d", attempt + 1, poll_max, gen_status)

        raise RuntimeError(f"LiblibAI poll exhausted after {poll_max} attempts")

    @staticmethod
    def _resolve_env(key: str) -> str:
        val = os.environ.get(key, "")
        if val:
            return val
        try:
            from app.config import get_settings
            cfg = get_settings()
            return str(getattr(cfg, key, ""))
        except Exception:
            return ""

    @staticmethod
    def _sign(uri: str, access_key: str, secret_key: str) -> str:
        ts = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        content = "&".join((uri, ts, nonce))
        digest = hmac.new(secret_key.encode(), content.encode(), hashlib.sha1).digest()
        sign = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return f"{uri}?AccessKey={access_key}&Signature={sign}&Timestamp={ts}&SignatureNonce={nonce}"

    @staticmethod
    def _resolve_aspect_ratio(spec: GenSpec) -> str:
        ar = spec.aspect_ratio
        if ar:
            ar_normalized = {"1:1": "square", "3:4": "portrait", "16:9": "landscape"}
            result = ar_normalized.get(ar.lower()) if isinstance(ar, str) else None
            if result:
                return result
            if ar.lower() in ("square", "portrait", "landscape"):
                return ar.lower()
        ratio = spec.width / spec.height
        if abs(ratio - 1.0) < 0.05:
            return "square"
        elif abs(ratio - 0.75) < 0.05:
            return "portrait"
        elif abs(ratio - 1.78) < 0.05:
            return "landscape"
        return "square"
