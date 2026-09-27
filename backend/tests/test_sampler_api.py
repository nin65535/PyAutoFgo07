import io

from fastapi.testclient import TestClient
from PIL import Image

from autofgo.sampler_api import MAX_IMAGE_BYTES, SamplerState, create_sampler_app
from autofgo.status_card_candidates import CardLayout


def _headers(state):
    return {
        "X-AutoFgo-Session-Id": state.security.session_id,
        "Authorization": f"Bearer {state.security.token}",
    }


def test_sampler_icon_is_available_in_page_and_tab(tmp_path):
    state = SamplerState(tmp_path / "manifest.json", tmp_path / "scenarios")
    client = TestClient(create_sampler_app(state))
    page = client.get("/")
    icon = client.get("/autofgo-icon.svg")

    assert page.status_code == 200
    assert page.text.count('src="/autofgo-icon.svg"') == 1
    assert 'rel="icon" type="image/svg+xml" href="/autofgo-icon.svg"' in page.text
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    assert "AutoFgo" in icon.text


def test_sampler_auth_and_image_limits(tmp_path):
    state = SamplerState(tmp_path / "manifest.json", tmp_path / "scenarios")
    client = TestClient(create_sampler_app(state))
    assert client.get("/api/catalog").status_code == 401
    assert client.get("/api/catalog", headers=_headers(state)).status_code == 200
    assert (
        client.post(
            "/api/image",
            headers={**_headers(state), "Content-Type": "text/plain"},
            content=b"hello",
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/image",
            headers={**_headers(state), "Content-Type": "image/png"},
            content=b"x" * (MAX_IMAGE_BYTES + 1),
        ).status_code
        == 413
    )
    output = io.BytesIO()
    Image.new("RGB", (20, 20)).save(output, format="PNG")
    assert (
        client.post(
            "/api/image",
            headers={**_headers(state), "Content-Type": "image/png"},
            content=output.getvalue(),
        ).status_code
        == 422
    )
    assert state.image is None


def test_scenario_name_normalization(tmp_path):
    directory = tmp_path / "scenarios"
    directory.mkdir()
    (directory / "one.json").write_text(
        '{"members":["キャストリア＋NP50","キャストリア guest","ダ・ヴィンチ（騎）"]}',
        encoding="utf-8",
    )
    state = SamplerState(tmp_path / "manifest.json", directory)
    assert [item["name"] for item in state.names()] == ["キャストリア", "ダ・ヴィンチ（騎）"]


def test_save_confirmed_candidate_and_discard_source(tmp_path):
    directory = tmp_path / "scenarios"
    directory.mkdir()
    (directory / "one.json").write_text('{"members":["アーラシュ"]}', encoding="utf-8")
    state = SamplerState(tmp_path / "references" / "manifest.json", directory)
    state.image = Image.new("RGB", (1920, 1080), "red")
    state.layout = CardLayout(
        (1920, 1080), (700, 300, 175, 44), tuple((750 + 206 * i, 400, 140, 180) for i in range(5))
    )
    state.source_id = "sample-source"
    client = TestClient(create_sampler_app(state))
    selection = {
        "characterName": "アーラシュ",
        "cardIndex": 0,
        "size": [105, 100],
        "candidateIndex": 0,
        "sourceId": "sample-source",
        "confirmed": True,
    }
    assert (
        client.post(
            "/api/references", headers=_headers(state), json={**selection, "confirmed": False}
        ).status_code
        == 422
    )
    assert not state.manifest.exists()
    response = client.post("/api/references", headers=_headers(state), json=selection)
    assert response.status_code == 200
    assert response.json()["reference"]["source"]["crop"] == [764, 397, 105, 100]
    assert state.image is None
    assert (state.manifest.parent / "images" / "アーラシュ-1-01.png").exists()
