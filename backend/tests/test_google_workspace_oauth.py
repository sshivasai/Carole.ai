import json
import uuid
def test_packaged_desktop_oauth_client_is_available():
    from core.api import google_auth_routes as google

    config, client_type = google._load_client_config()
    assert client_type == "installed"
    assert config[client_type]["client_id"].endswith(".apps.googleusercontent.com")
    assert "client_secret" not in config[client_type]


def test_public_desktop_client_uses_pkce_token_exchange_without_secret():
    from core.api import google_auth_routes as google

    class FakeSession:
        def __init__(self):
            self.calls = []

        def fetch_token(self, token_uri, **kwargs):
            self.calls.append((token_uri, kwargs))
            return {"access_token": "token"}

    class FakeFlow:
        def __init__(self):
            self.oauth2session = FakeSession()
            self.code_verifier = "pkce-verifier"

        def fetch_token(self, **_kwargs):
            raise AssertionError("Public clients must not use Flow.fetch_token")

    flow = FakeFlow()
    config = {
        "installed": {
            "client_id": "client.apps.googleusercontent.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    result = google._fetch_oauth_token(flow, config, "installed", "auth-code")

    assert result == {"access_token": "token"}
    assert flow.oauth2session.calls == [
        (
            "https://oauth2.googleapis.com/token",
            {
                "code": "auth-code",
                "code_verifier": "pkce-verifier",
                "include_client_id": True,
                "client_secret": None,
            },
        )
    ]


def test_google_scopes_match_workspace_tools():
    from core.api.google_auth_routes import SCOPES

    assert "https://www.googleapis.com/auth/gmail.modify" in SCOPES
    assert "https://www.googleapis.com/auth/calendar.events" in SCOPES
    assert "https://www.googleapis.com/auth/tasks" in SCOPES
    assert "https://mail.google.com/" not in SCOPES
    assert "https://www.googleapis.com/auth/gmail.readonly" not in SCOPES


def test_legacy_token_is_migrated_to_os_vault(tmp_path, monkeypatch):
    from core.api import google_auth_routes as google

    user_id = str(uuid.uuid4())
    monkeypatch.setattr(google, "CAROLE_HOME_DIR", tmp_path)
    token_path = google._token_path(user_id)
    token_path.parent.mkdir(parents=True)
    token_path.write_text(json.dumps({
        "token": "access-token",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client.apps.googleusercontent.com",
        "client_secret": "public-desktop-secret",
        "scopes": google.SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }), encoding="utf-8")

    saved = {}
    monkeypatch.setattr(google.google_token_store, "load", lambda _user_id: None)
    monkeypatch.setattr(
        google.google_token_store,
        "save",
        lambda target_user, token_json: saved.__setitem__(target_user, token_json),
    )

    credentials = google._load_token(user_id)
    assert credentials is not None
    assert user_id in saved
    assert not token_path.exists()


def test_workspace_mutations_require_human_approval():
    from core.tools.tool_executor import register_builtin_tools
    from core.tools.tool_registry import ToolRegistry

    register_builtin_tools()
    human_tools = {
        "send_email",
        "manage_email",
        "create_meeting",
        "update_calendar_event",
        "delete_calendar_event",
        "create_google_task",
        "update_google_task",
        "delete_google_task",
    }
    for name in human_tools:
        assert ToolRegistry.get(name).permission_default == "human"

    for name in {"list_emails", "read_email", "list_calendar_events", "list_google_tasks"}:
        assert ToolRegistry.get(name).permission_default == "safe"
