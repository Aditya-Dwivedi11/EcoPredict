import json
import os
import sys
from pathlib import Path

import ee

credentials_path = Path.home() / ".config" / "earthengine" / "credentials"

print("=== EcoPredict Earth Engine Setup ===")
print("Python executable:", sys.executable)
print("Earth Engine package:", ee.__file__)
print("Home directory:", Path.home())
print("EE_CONFIG_FILE set:", bool(os.environ.get("EE_CONFIG_FILE")))
print("Expected credentials file:", credentials_path)
print("Credentials file exists:", credentials_path.is_file())

if credentials_path.is_file():
    try:
        stored = json.loads(credentials_path.read_text())
        print("Credential file is valid JSON: True")
        print("Credential fields:", ", ".join(sorted(stored.keys())))
        print("Refresh token present:", bool(stored.get("refresh_token")))
    except Exception as exc:
        print("Credential file could not be read as valid JSON:", type(exc).__name__)

print("\nStarting fresh authorization in this Python environment.")
print("Complete Google's browser flow; do not share the code or token.")

try:
    ee.Authenticate(force=True, auth_mode="notebook")
except Exception as exc:
    print("\nAUTHENTICATION FAILED")
    print(type(exc).__name__ + ":", str(exc))
    sys.exit(1)

print("\nChecking saved Earth Engine credentials...")
try:
    credentials = ee.data.get_persistent_credentials()
    print("Persistent credentials loaded:", credentials is not None)
except Exception as exc:
    print("Credentials still unavailable:", type(exc).__name__, str(exc))
    sys.exit(2)

project_id = os.environ.get("EE_PROJECT_ID", "").strip()
if not project_id:
    project_id = input(
        "\nEnter your registered Google Cloud Project ID (not its display name): "
    ).strip()

if not project_id:
    print("No project ID supplied. Authentication may be saved, but initialization was not tested.")
    sys.exit(3)

print("\nTesting Earth Engine initialization...")
try:
    ee.Initialize(project=project_id)
    result = ee.String("EcoPredict connection successful").getInfo()
    print("SUCCESS:", result)
    print("Earth Engine is authenticated and initialized.")
except Exception as exc:
    print("\nINITIALIZATION FAILED")
    print(type(exc).__name__ + ":", str(exc))
    print(
        "Authentication may be working, but the project ID, API enablement, "
        "Earth Engine registration, or permissions may need attention."
    )
    sys.exit(4)
