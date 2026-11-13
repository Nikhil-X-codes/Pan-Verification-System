import asyncio


class VendorA:
    name = "Vendor A"

    async def verify(self, pan: str, faulty: bool) -> dict:
        await simulate(pan, faulty)
        if pan == "ABCPE0000F" or pan not in SAMPLES:
            return {"pan_status": "NOT_FOUND"}
        return {"pan_status": "VALID", "full_name": "RAHUL SHARMA"}


class VendorB:
    name = "Vendor B"

    async def verify(self, pan: str, faulty: bool) -> dict:
        await simulate(pan, faulty)
        if pan == "ABCPE0000F" or pan not in SAMPLES:
            return {"result": {"valid": False}}
        return {"result": {"valid": True, "name": "RAHUL SHARMA"}}


SAMPLES = {"ABCPE1234F", "ABCPE0000F", "ABCPE9999F", "ABCPE8888F"}


async def simulate(pan: str, faulty: bool) -> None:
    if faulty and pan == "ABCPE9999F":
        await asyncio.sleep(5)
    await asyncio.sleep(0.05)
    if faulty and pan == "ABCPE8888F":
        raise RuntimeError("Simulated provider failure")


def normalize(raw: dict) -> tuple[bool, str | None]:
    if "pan_status" in raw:
        return raw["pan_status"] == "VALID", raw.get("full_name")
    return raw["result"]["valid"], raw["result"].get("name")
