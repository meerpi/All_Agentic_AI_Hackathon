import os
import shutil
import glob
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
BACKUP_PATH = os.path.join(BASE_DIR, "token_backup.json")

# Backup existing token
if os.path.exists(TOKEN_PATH):
    shutil.copyfile(TOKEN_PATH, BACKUP_PATH)
    os.remove(TOKEN_PATH)
    print(f"Backed up existing token to {BACKUP_PATH} and cleared active token.json.")

# Find client secret file
client_secrets = glob.glob(os.path.join(BASE_DIR, "client_secret_*.json"))
if not client_secrets and os.path.exists(os.path.join(BASE_DIR, "credentials.json")):
    client_secrets = [os.path.join(BASE_DIR, "credentials.json")]

if not client_secrets:
    print("Error: No client_secret_*.json or credentials.json found in project root.")
    exit(1)

secret_file = client_secrets[0]
print(f"Using OAuth client secret: {os.path.basename(secret_file)}")
print("Starting Google OAuth consent flow. Opening browser window...")

flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
creds = flow.run_local_server(port=0, prompt="select_account")

with open(TOKEN_PATH, "w") as token_file:
    token_file.write(creds.to_json())

print(f"\n[SUCCESS] Google OAuth consent completed! New token saved to {TOKEN_PATH}.")

# Verify connected account
try:
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Connected Account: {profile.get('emailAddress')}")
except Exception as e:
    print(f"Could not verify profile: {e}")
