import subprocess
import requests

# Install required libraries
subprocess.run(['pip', 'install', 'PyYAML', 'requests'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Import after installation
import yaml

# GitHub API token and details
token = ''
username = 'ta1789'
repo_name = 'TDSProject_Test'

# GitHub Action YAML content
action_content = {
    "name": "CI",
    "on": {
        "push": {
            "branches": ["main"]
        }
    },
    "jobs": {
        "test": {
            "runs-on": "ubuntu-latest",
            "steps": [
                {
                    "name": "tanmay.mehrotra@gramener.com",
                    "run": "echo 'Hello, world!'"
                }
            ]
        }
    }
}

# Create GitHub action file in the repository
url = f'https://api.github.com/repos/{username}/{repo_name}/contents/.github/workflows/ci.yml'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Prepare the request data
data = {
    "message": "Add GitHub Action",
    "content": yaml.dump(action_content).encode('base64').decode(),
    "branch": "main"  # Specify the branch if necessary
}

# Sending the request to create the GitHub Action
response = requests.put(url, headers=headers, json=data)
if response.status_code == 201:
    print("GitHub Action created successfully.")
else:
    print("Failed to create GitHub Action:", response.json())

# Repository URL
repo_url = f'https://github.com/{username}/{repo_name}'
print("Repository URL:", repo_url)