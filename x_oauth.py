
import requests

X_CLIENT_ID = "RlE4SGZaSVlBMmViODY1RU9kSU06MTpjaQ"
X_CLIENT_SECRET = "8HisN_ad5Nn_tdkdmQY-oJiE01w7G1CEVo5oD3F6KaLAQb4q6i"
CODE_VERIFIER = "B-Rn4NNzwWMVZVN8ktGG4wNOsXyypexHuxwGOIAcmFg"
AUTH_CODE = "B-Rn4NNzwWMVZVN8ktGG4wNOsXyypexHuxwGOIAcmFg"
url = "https://api.x.com/2/oauth2/token"

data = {
    "grant_type": "authorization_code",
    "code": AUTH_CODE,
    "redirect_uri": "http://localhost:8765/callback/x",
    "client_id": X_CLIENT_ID,
    "code_verifier": CODE_VERIFIER
}

headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(
    url,
    headers=headers,
    data=data,
    auth=(X_CLIENT_ID, X_CLIENT_SECRET)
)

print("Status:", response.status_code)
print("Response:", response.text)


