import json
import sys
import urllib.request


def extract_audio_url(raw_text: str) -> str:
    audio_url = ""
    for line in raw_text.splitlines():
        if line.startswith("data:"):
            try:
                payload = json.loads(line.replace("data:", "", 1).strip())
            except Exception:
                continue
            if isinstance(payload, dict):
                data_list = payload.get("data")
                if isinstance(data_list, list) and data_list:
                    last = data_list[-1]
                    if isinstance(last, dict):
                        audio_url = last.get("url") or last.get("path") or ""
                    elif isinstance(last, str):
                        audio_url = last
            if audio_url:
                return audio_url

    try:
        payload = json.loads(raw_text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        data_list = payload.get("data")
        if isinstance(data_list, list) and data_list:
            last = data_list[-1]
            if isinstance(last, dict):
                return last.get("url") or last.get("path") or ""
            if isinstance(last, str):
                return last
    return ""


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python tonyassi_test.py <sample_url> [text] [base_url]")
        return 1

    sample_url = sys.argv[1]
    text = sys.argv[2] if len(sys.argv) > 2 else "안녕하세요"
    base_url = sys.argv[3] if len(sys.argv) > 3 else "https://tonyassi-voice-clone.hf.space"

    payload = {
        "data": [
            text,
            {
                "path": sample_url,
                "meta": {"_type": "gradio.FileData"}
            }
        ]
    }

    call_url = f"{base_url}/gradio_api/call/clone"
    req = urllib.request.Request(
        call_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)

    event_id = data.get("event_id") or data.get("id")
    if not event_id:
        print("No event_id in response:", data)
        return 2

    result_url = f"{base_url}/gradio_api/call/clone/{event_id}"
    with urllib.request.urlopen(result_url, timeout=300) as resp:
        raw_text = resp.read().decode("utf-8", "ignore")

    audio_url = extract_audio_url(raw_text)
    if not audio_url:
        print("No audio URL found in response")
        return 3

    output_path = "tonyassi_output.mp3"
    urllib.request.urlretrieve(audio_url, output_path)
    print("audio_url:", audio_url)
    print("saved:", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
